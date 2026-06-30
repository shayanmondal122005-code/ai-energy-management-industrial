"""Detection engine — wires baseline + gate + detectors over real readings.

Aggregates raw readings + modeled env into the shapes each detector needs, routes
every intraday Tier-1 deviation through the environmental gate, reconciles drafts
into the AlertStore, and computes site health + recovery (M&V) reports.

The "expected" baseline always uses the SATELLITE/forecast env (the server-side
model), never the site's own generation — that is the whole point of weather
normalization. Combining the in-house EMS forecast (variability/clear-sky) with
the satellite POA is what lets the gate tell a real dip from a passing cloud.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime

from backend.services.solar_om.baseline import expected_energy_kwh, expected_power_w
from backend.services.solar_om.detectors.base import InMemoryAlertStore
from backend.services.solar_om.detectors.inverter_health import (
    InvIntervalSample,
    detect_inverter_derate,
    detect_inverter_outage,
)
from backend.services.solar_om.detectors.safety import (
    detect_arc_fault,
    detect_ground_fault,
    detect_open_or_degraded_string,
    detect_riso_trend,
)
from backend.services.solar_om.detectors.soiling import detect_soiling
from backend.services.solar_om.detectors.string_mppt import (
    detect_string_underperformance,
    string_current_ratio,
)
from backend.services.solar_om.environment import EnvironmentSource
from backend.services.solar_om.forecast import ForecastWindow
from backend.services.solar_om.gate import (
    GateAction,
    GateConfig,
    GateContext,
    assess_coherence,
    environmental_gate,
    poa_dropped,
)
from backend.services.solar_om.models import AlertDraft, Inverter, Plant, Reading, Severity, StringSpec
from backend.services.solar_om.tariff import Tariff


# ── aggregation ──────────────────────────────────────────────────────────────
def aggregate_inverter_samples(
    plant: Plant, intervals: list[list[Reading]], env_source: EnvironmentSource,
) -> dict[str, list[InvIntervalSample]]:
    """Per inverter: a time-ordered list of (poa, ac_power, expected_w) samples,
    where expected_w is the SATELLITE-modeled plant expectation × the inverter's
    rated share of the plant."""
    out: dict[str, list[InvIntervalSample]] = {}
    for interval in intervals:
        inv_levels = [r for r in interval if r.string_id is None]
        if not inv_levels:
            continue
        ts = inv_levels[0].ts
        env = env_source.get(plant, ts)
        plant_exp_w = expected_power_w(plant, env)
        share = 1.0 / len(inv_levels) if inv_levels else 1.0
        for r in inv_levels:
            out.setdefault(r.inverter_id, []).append(InvIntervalSample(
                ts=ts, poa_wm2=env.poa_wm2, ac_power_w=r.ac_power_w or 0.0,
                expected_w=plant_exp_w * share))
    return out


def aggregate_string_ratios(intervals: list[list[Reading]]) -> dict[str, dict]:
    """Per string: ratio-to-peer-median series + the hours it ran low (for shading)."""
    out: dict[str, dict] = {}
    for interval in intervals:
        strings = [r for r in interval if r.string_id is not None]
        by_inv: dict[str, list[Reading]] = {}
        for r in strings:
            by_inv.setdefault(r.inverter_id, []).append(r)
        for inv_id, rs in by_inv.items():
            for r in rs:
                peers = [p.dc_current for p in rs if p.string_id != r.string_id]
                ratio = string_current_ratio(r.dc_current or 0.0, peers)
                d = out.setdefault(r.string_id, {"ratios": [], "low_hours": set(),
                                                 "last_v": 0.0, "last_i": 0.0})
                d["ratios"].append(ratio)
                d["last_v"] = r.dc_voltage or 0.0
                d["last_i"] = r.dc_current or 0.0
                if ratio < 1.0 - GateConfig().drop_threshold:
                    d["low_hours"].add(r.ts.hour)
    return out


# ── intraday detection (gated) ───────────────────────────────────────────────
@dataclass
class IntradayConfig:
    interval_hours: float = 0.25
    gate: GateConfig = None  # type: ignore

    def __post_init__(self):
        if self.gate is None:
            self.gate = GateConfig()


def _gate_context(scope: str, *, coherent: bool, localized: bool,
                  minutes: float, intervals: int, forecast: ForecastWindow,
                  poa_drop: bool) -> GateContext:
    return GateContext(
        scope=scope, coherent=coherent, localized=localized,
        intervals_persisted=intervals, minutes_persisted=minutes,
        forecast_variability_index=forecast.cloud_variability_index,
        clear_sky=forecast.clear_sky_flag, satellite_poa_dropped=poa_drop)


def run_intraday(
    plant: Plant, inverters: list[Inverter], strings: list[StringSpec],
    intervals: list[list[Reading]], env_source: EnvironmentSource,
    forecast: ForecastWindow, tariff: Tariff, store: InMemoryAlertStore,
    *, cfg: IntradayConfig | None = None,
) -> None:
    cfg = cfg or IntradayConfig()
    if not intervals:
        return
    last_ts = intervals[-1][0].ts if intervals[-1] else intervals[0][0].ts
    rate = tariff.rupee_per_kwh(last_ts)

    inv_samples = aggregate_inverter_samples(plant, intervals, env_source)
    str_data = aggregate_string_ratios(intervals)
    str_inv = {s.id: s.inverter_id for s in strings}

    # Did the modeled SATELLITE POA itself drop vs the forecast clear-sky peak? If the
    # satellite already shows the cloud, expected drops too and there is no deviation;
    # the dangerous case is a real cloud the coarse satellite/forecast missed.
    clear_poa = max(forecast.poa_forecast_wm2) if forecast.poa_forecast_wm2 else 0.0
    last_env = env_source.get(plant, last_ts)
    poa_drop = poa_dropped(last_env.poa_wm2, clear_poa)

    # Per-inverter deficit vs expected at the latest interval → coherence.
    inv_deficits = {}
    for inv_id, samples in inv_samples.items():
        if samples and samples[-1].expected_w > 0:
            inv_deficits[inv_id] = max(0.0, 1.0 - samples[-1].ac_power_w / samples[-1].expected_w)
    coherent_inv, _ = assess_coherence(inv_deficits, cfg.gate)

    drafts: list[AlertDraft] = []

    # 0) GATE SHOWCASE — coherent plant-wide generation dip.
    # When ALL units fall below the modeled expectation together, that is the cloud
    # signature. Route it through the gate: a transient coherent dip is SUPPRESSED and
    # logged for audit (this is what kills cloud_pass false alarms). A sustained, real
    # loss PASSES and is then owned by the dedicated outage/derate detectors below — so
    # it is never double-counted here.
    dip_run = _trailing_plant_deficit_run(inv_samples, cfg.gate.drop_threshold)
    if inv_deficits and coherent_inv and dip_run > 0:
        ctx = _gate_context("plant", coherent=True, localized=False,
                            minutes=dip_run * cfg.interval_hours * 60.0, intervals=dip_run,
                            forecast=forecast, poa_drop=poa_drop)
        decision = environmental_gate(ctx, cfg.gate)
        if decision.action == GateAction.SUPPRESS:
            store.record_suppressed(
                AlertDraft(plant_id=plant.id, type="generation_shortfall", severity=Severity.INFO,
                           recommended_action="Coherent transient dip — environmental, no action",
                           evidence={"deficit_intervals": dip_run}),
                last_ts, decision.reason)

    # 1) OUTAGE + DERATE (inverter-level, gated)
    for inv in inverters:
        samples = inv_samples.get(inv.id, [])
        localized = (inv_deficits.get(inv.id, 0.0) >= cfg.gate.drop_threshold) and not coherent_inv
        outage = detect_inverter_outage(plant.id, inv.id, samples, tariff_rate=rate,
                                        interval_hours=cfg.interval_hours)
        if outage is not None:
            n = _trailing_outage_n(samples)
            ctx = _gate_context("inverter", coherent=coherent_inv, localized=localized,
                                minutes=n * cfg.interval_hours * 60.0, intervals=n,
                                forecast=forecast, poa_drop=poa_drop)
            _apply_gate(outage, ctx, cfg.gate, store, last_ts, drafts)
        derate = detect_inverter_derate(plant.id, inv.id, samples, clipping_kw=inv.clipping_kw)
        if derate is not None:
            n = _derate_low_n(samples, inv.clipping_kw)
            ctx = _gate_context("inverter", coherent=coherent_inv, localized=localized,
                                minutes=n * cfg.interval_hours * 60.0, intervals=n,
                                forecast=forecast, poa_drop=poa_drop)
            _apply_gate(derate, ctx, cfg.gate, store, last_ts, drafts)

    # 2) STRING / MPPT + open-vs-degraded. A coherent cloud keeps every string's
    # peer-ratio ≈ 1, so this layer is inherently cloud-robust; a localized drop passes.
    plant_envs = [env_source.get(plant, i[0].ts) for i in intervals if i]
    plant_exp_kwh = expected_energy_kwh(plant, plant_envs, cfg.interval_hours)
    str_deficits = {sid: max(0.0, 1.0 - (statistics.median(d["ratios"]) if d["ratios"] else 1.0))
                    for sid, d in str_data.items()}
    for s in strings:
        d = str_data.get(s.id)
        if not d:
            continue
        peers = {sid: dev for sid, dev in str_deficits.items() if str_inv.get(sid) == s.inverter_id}
        coherent_s, localized_s = assess_coherence(peers, cfg.gate)
        localized_this = localized_s and str_deficits.get(s.id, 0.0) >= cfg.gate.drop_threshold
        draft = detect_string_underperformance(
            plant.id, s.inverter_id, s.id, d["ratios"],
            expected_kwh_window=plant_exp_kwh, rated_share=s.rated_share_fraction,
            tariff_rate=rate, clock_locked=False)
        if draft is not None:
            ctx = _gate_context("string", coherent=coherent_s, localized=localized_this,
                                minutes=len(d["ratios"]) * cfg.interval_hours * 60,
                                intervals=len(d["ratios"]), forecast=forecast, poa_drop=poa_drop)
            _apply_gate(draft, ctx, cfg.gate, store, last_ts, drafts)
        ov = detect_open_or_degraded_string(
            plant.id, s.inverter_id, s.id, dc_current=d["last_i"], dc_voltage=d["last_v"],
            peer_deficit_frac=str_deficits.get(s.id, 0.0), persistent=len(d["ratios"]) >= 3,
            rated_share=s.rated_share_fraction, expected_kwh_window=plant_exp_kwh, tariff_rate=rate)
        if ov is not None:
            drafts.append(ov)

    # 3) SAFETY (Tier-1.5, ungated — register reads)
    for inv in inverters:
        last_inv = _last_inv_reading(intervals, inv.id)
        if last_inv is None:
            continue
        gf = detect_ground_fault(plant.id, inv.id, ground_fault_flag=last_inv.ground_fault,
                                 riso_kohm=last_inv.riso_kohm,
                                 riso_threshold_kohm=inv.riso_threshold_kohm)
        arc = detect_arc_fault(plant.id, inv.id, arc_fault_flag=last_inv.arc_fault)
        drafts.extend(d for d in (gf, arc) if d is not None)

    drafts = _dedupe_root_cause(drafts)

    open_types = {"inverter_outage", "inverter_derate", "string_underperformance",
                  "string_open", "string_degraded", "ground_fault", "arc_fault"}
    store.reconcile(drafts, last_ts, scope_types=open_types)


def _dedupe_root_cause(drafts: list[AlertDraft]) -> list[AlertDraft]:
    """Collapse alerts that are the SAME physical fault seen at different levels — a
    dead inverter is an outage, not also a derate; an open string's refined diagnosis
    (string_open) supersedes the generic underperformance. This is alert hygiene, NOT
    fault localization (we don't pinpoint *where* in the string)."""
    outage_invs = {d.inverter_id for d in drafts if d.type == "inverter_outage"}
    open_strings = {d.string_id for d in drafts if d.type == "string_open"}
    invs_with_string_fault = {d.inverter_id for d in drafts if d.type == "string_open"}
    kept = []
    for d in drafts:
        if d.type == "inverter_derate" and d.inverter_id in (outage_invs | invs_with_string_fault):
            continue  # the outage / string fault already explains this inverter's shortfall
        if d.type == "string_underperformance" and d.string_id in open_strings:
            continue  # string_open is the refined diagnosis of the same string
        kept.append(d)
    return kept


def _apply_gate(draft, ctx, gcfg, store, ts, drafts):
    decision = environmental_gate(ctx, gcfg)
    if decision.action == GateAction.SUPPRESS:
        store.record_suppressed(draft, ts, decision.reason)
        return
    if decision.action == GateAction.DOWNWEIGHT:
        draft.confidence = round(draft.confidence * decision.confidence_factor, 3)
        draft.evidence = {**(draft.evidence or {}), "gate": decision.reason}
    drafts.append(draft)


def _trailing_plant_deficit_run(inv_samples: dict[str, list[InvIntervalSample]], thresh: float) -> int:
    """Trailing count of intervals where the PLANT total fell below expected by ≥ thresh."""
    if not inv_samples:
        return 0
    n = min(len(v) for v in inv_samples.values())
    run = 0
    for i in range(n - 1, -1, -1):
        exp = sum(v[i].expected_w for v in inv_samples.values())
        act = sum(v[i].ac_power_w for v in inv_samples.values())
        if exp > 0 and (1.0 - act / exp) >= thresh:
            run += 1
        else:
            break
    return run


def _trailing_outage_n(samples) -> int:
    from backend.services.solar_om.detectors.inverter_health import _trailing_outage_run
    return len(_trailing_outage_run(samples, 200.0))


def _derate_low_n(samples, clipping_kw) -> int:
    considered = [s for s in samples if s.expected_w > 0
                  and (clipping_kw is None or s.expected_w < clipping_kw * 1000.0)]
    return sum(1 for s in considered if (1.0 - s.ac_power_w / s.expected_w) >= 0.15)


def _last_inv_reading(intervals, inv_id) -> Reading | None:
    for interval in reversed(intervals):
        for r in interval:
            if r.inverter_id == inv_id and r.string_id is None:
                return r
    return None


# ── trend detection (daily/weekly) ───────────────────────────────────────────
def run_trends(
    plant: Plant, inverters: list[Inverter], store: InMemoryAlertStore,
    *, pr_tcorr_series: list[float] | None = None, days_since_clean: int = 0,
    expected_kwh_day: float = 0.0, tariff_rate: float = 0.0, cleaning_cost: float = 3000.0,
    weekly_riso_by_inverter: dict[str, list[float]] | None = None,
    ts: datetime | None = None,
) -> None:
    ts = ts or datetime.now()
    drafts: list[AlertDraft] = []
    if pr_tcorr_series:
        soil = detect_soiling(plant.id, pr_tcorr_series, days_since_clean=days_since_clean,
                              expected_kwh_day=expected_kwh_day, tariff_rate=tariff_rate,
                              cleaning_cost=cleaning_cost)
        if soil is not None:
            drafts.append(soil)
    for inv in inverters:
        series = (weekly_riso_by_inverter or {}).get(inv.id)
        if series:
            rt = detect_riso_trend(plant.id, inv.id, series)
            if rt is not None:
                drafts.append(rt)
    store.reconcile(drafts, ts, scope_types={"soiling", "insulation_trend"})


def run_meter_consistency(plant: Plant, meter_kwh: float, inverter_sum_kwh: float,
                          store: InMemoryAlertStore, ts: datetime) -> None:
    """Cross-check the revenue solar meter total against summed inverter AC (the merged
    EMS+O&M system has both feeds on one bus). Opens/closes a data-integrity alert."""
    from backend.services.solar_om.detectors.meter_consistency import detect_meter_inverter_divergence
    d = detect_meter_inverter_divergence(plant.id, meter_kwh, inverter_sum_kwh)
    store.reconcile([d] if d else [], ts, scope_types={"meter_inverter_divergence"})


# ── health + verification (M&V) ──────────────────────────────────────────────
def site_health(plant: Plant, store: InMemoryAlertStore, *, pr: float | None = None,
                pr_tcorr: float | None = None) -> dict:
    open_alerts = store.open_alerts()
    total_rs_day = sum(a.get("rupee_impact_per_day") or 0.0 for a in open_alerts)
    return {
        "plant_id": plant.id, "calibrated": plant.calibrated,
        "pr": pr, "pr_tcorr": pr_tcorr,
        "open_alerts": len(open_alerts),
        "total_rupee_impact_per_day": round(total_rs_day, 2),
        "alerts": open_alerts,
    }


def verify_recovery(store: InMemoryAlertStore, key: tuple, ts: datetime, *,
                    pr_tcorr_before: float, pr_tcorr_after: float,
                    expected_kwh_day: float, tariff_rate: float,
                    recovery_threshold: float = 0.02) -> dict | None:
    """After a cleaning/repair event, check for the expected PR_tcorr step-up. If it
    recovered, close the alert and emit an IPMVP-style recovery (M&V) report:
    baseline vs post-fix kWh and the ₹ recovered that powers gainshare."""
    step = pr_tcorr_after - pr_tcorr_before
    if step < recovery_threshold:
        return None
    regained_frac = step / pr_tcorr_before if pr_tcorr_before > 0 else 0.0
    kwh_regained_day = round(regained_frac * expected_kwh_day, 1)
    report = {
        "pr_tcorr_before": round(pr_tcorr_before, 4),
        "pr_tcorr_after": round(pr_tcorr_after, 4),
        "pr_tcorr_step": round(step, 4),
        "kwh_regained_per_day": kwh_regained_day,
        "rupee_recovered_per_day": round(kwh_regained_day * tariff_rate, 2),
        "verified_at": ts.isoformat(),
    }
    store.close(key, ts, reason="recovery verified", recovery=report)
    return report
