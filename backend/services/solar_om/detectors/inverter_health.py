"""Detector 2 — INVERTER DOWNTIME / HEALTH.

  OUTAGE (critical)   : POA > floor AND ac_power ≈ 0 sustained > 15 min →
                        ₹ = expected_kwh_during_outage × tariff, live-accumulating.
  DERATE (investigate): ac_power persistently capped below expected OUTSIDE the
                        clipping window (so it isn't legitimate inverter clipping).
  PREDICTIVE (info)   : a recurring fault_code whose weekly count is RISING →
                        schedule maintenance before it becomes an outage.

Outage/derate are coherent across all strings of the inverter, so they are routed
through the environmental gate by the caller (a fleet-wide POA cloud must not read
as an outage); the persistence requirement (>15 min) is itself a gate layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.services.solar_om.models import AlertDraft, Severity


@dataclass(frozen=True)
class InvIntervalSample:
    ts: datetime
    poa_wm2: float
    ac_power_w: float
    expected_w: float


def _trailing_outage_run(samples: list[InvIntervalSample], poa_floor: float) -> list[InvIntervalSample]:
    """The current (trailing) consecutive run where the sun is up but power is ~0.

    Trailing low-sun (dusk/night) intervals carry no information — at POA below the
    floor you cannot tell "out" from "dark" — so they are SKIPPED rather than allowed
    to mask a daytime outage that is still ongoing at last light.
    """
    i = len(samples) - 1
    while i >= 0 and samples[i].poa_wm2 <= poa_floor:
        i -= 1   # skip trailing dusk/night
    run: list[InvIntervalSample] = []
    while i >= 0:
        s = samples[i]
        if s.poa_wm2 > poa_floor and s.ac_power_w <= max(50.0, 0.01 * s.expected_w):
            run.append(s)
            i -= 1
        else:
            break
    return list(reversed(run))


def detect_inverter_outage(
    plant_id: str, inverter_id: str, samples: list[InvIntervalSample],
    *, tariff_rate: float, interval_hours: float,
    poa_floor: float = 200.0, min_minutes: float = 15.0,
) -> AlertDraft | None:
    run = _trailing_outage_run(samples, poa_floor)
    minutes = len(run) * interval_hours * 60.0
    if not run or minutes <= min_minutes:   # strictly > min_minutes (spec: ">15 min")
        return None
    lost_kwh = sum(s.expected_w for s in run) / 1000.0 * interval_hours
    rs_lost = round(lost_kwh * tariff_rate, 2)
    outage_hours = max(1e-9, minutes / 60.0)
    # Extrapolate the current loss rate to a full day for the headline ₹/day figure.
    rs_per_day = round(lost_kwh / outage_hours * 24.0 * tariff_rate, 2)
    return AlertDraft(
        plant_id=plant_id, inverter_id=inverter_id, type="inverter_outage",
        severity=Severity.CRITICAL,
        recommended_action="Inverter not exporting under sun — dispatch / restart; check AC breaker & comms",
        confidence=1.0,
        rupee_impact_per_day=rs_per_day, rupee_accumulated=rs_lost,
        evidence={
            "outage_minutes": round(minutes, 1),
            "lost_kwh_so_far": round(lost_kwh, 2),
            "poa_wm2": round(run[-1].poa_wm2, 1),
            "ac_power_w": round(run[-1].ac_power_w, 1),
        },
    )


def detect_inverter_derate(
    plant_id: str, inverter_id: str, samples: list[InvIntervalSample],
    *, clipping_kw: float | None = None, theta: float = 0.15, min_intervals: int = 4,
) -> AlertDraft | None:
    """Persistent shortfall vs expected, excluding intervals that are legitimately
    clipping (expected ≥ clipping_kw)."""
    considered = [s for s in samples if s.expected_w > 0
                  and (clipping_kw is None or s.expected_w < clipping_kw * 1000.0)]
    if len(considered) < min_intervals:
        return None
    shortfalls = [1.0 - s.ac_power_w / s.expected_w for s in considered]
    low = [d for d in shortfalls if d >= theta]
    if len(low) < min_intervals:
        return None
    mean_short = sum(shortfalls) / len(shortfalls)
    return AlertDraft(
        plant_id=plant_id, inverter_id=inverter_id, type="inverter_derate",
        severity=Severity.INVESTIGATE,
        recommended_action="Inverter capped below expected outside clipping — check temperature/derating limits",
        confidence=0.7,
        evidence={"mean_shortfall_pct": round(mean_short * 100, 1),
                  "intervals_low": len(low), "theta_pct": theta * 100},
    )


def detect_predictive_faultcode(
    plant_id: str, inverter_id: str, code: int, weekly_counts: list[int],
) -> AlertDraft | None:
    """A recurring fault code whose weekly occurrence is trending UP → schedule
    service before it escalates to an outage."""
    if len(weekly_counts) < 3:
        return None
    rising = all(weekly_counts[i] <= weekly_counts[i + 1] for i in range(len(weekly_counts) - 1))
    if not (rising and weekly_counts[-1] > weekly_counts[0]):
        return None
    return AlertDraft(
        plant_id=plant_id, inverter_id=inverter_id, type="inverter_predictive",
        severity=Severity.INFO,
        recommended_action=f"Recurring fault code {code} rising week-over-week — schedule preventive service",
        confidence=0.6,
        evidence={"fault_code": code, "weekly_counts": list(weekly_counts)},
    )
