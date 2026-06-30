"""Tier-1.5 — ELECTRICAL SAFETY from inverter registers (read-only, risk-framed).

These read protective values the inverter ALREADY computes — we do NOT model them,
we surface and TREND them. Lead with risk, not rupees (rupee_impact may be null).

  4) GROUND FAULT     : ground_fault flag OR Riso < threshold → CRITICAL, isolate+inspect.
  5) INSULATION TREND : Riso declining week-over-week even ABOVE threshold →
                        INVESTIGATE (the predictive win — schedule before a hard trip).
  6) ARC FAULT        : arc_fault flag → CRITICAL, fire risk, dispatch immediately.
  7) OPEN vs DEGRADED : I≈0 with V present → OPEN circuit (broken wire/fuse/diode);
                        8–25% low, persistent, NOT recovering on cleaning, NOT
                        clock-locked → series-resistance / connector degradation.
"""
from __future__ import annotations

import numpy as np

from backend.services.solar_om.models import AlertDraft, Severity

OPEN_CURRENT_EPS_A = 0.5     # below this DC current is effectively "no current"
V_PRESENT_MIN = 50.0         # DC voltage present (string is illuminated/connected)
OPEN_REL_DEFICIT = 0.5       # string must be dead RELATIVE to producing peers (not just dark)
DEGRADED_LOW = 0.08
DEGRADED_HIGH = 0.25


def detect_ground_fault(plant_id: str, inverter_id: str, *,
                        ground_fault_flag: bool | None, riso_kohm: float | None,
                        riso_threshold_kohm: float | None) -> AlertDraft | None:
    below = (riso_kohm is not None and riso_threshold_kohm is not None
             and riso_kohm < riso_threshold_kohm)
    if not (ground_fault_flag or below):
        return None
    why = "ground-fault flag set" if ground_fault_flag else f"Riso {riso_kohm}kΩ < {riso_threshold_kohm}kΩ threshold"
    return AlertDraft(
        plant_id=plant_id, inverter_id=inverter_id, type="ground_fault",
        severity=Severity.CRITICAL,
        recommended_action="Isolate the array and inspect — do not operate",
        confidence=1.0,
        risk_note=f"Electric shock / fire risk ({why}). Insulation to ground compromised.",
        evidence={"ground_fault_flag": bool(ground_fault_flag), "riso_kohm": riso_kohm,
                  "riso_threshold_kohm": riso_threshold_kohm},
    )


def detect_riso_trend(plant_id: str, inverter_id: str, weekly_riso_kohm: list[float],
                      *, min_weeks: int = 3, min_drop_frac: float = 0.1) -> AlertDraft | None:
    """Even ABOVE threshold: a steady week-over-week Riso decline predicts a future
    hard ground-fault trip. Fit a slope; fire on a sustained downward trend."""
    vals = [v for v in weekly_riso_kohm if v is not None]
    if len(vals) < min_weeks:
        return None
    x = np.arange(len(vals), dtype=float)
    slope = float(np.polyfit(x, np.array(vals, dtype=float), 1)[0])
    drop_frac = (vals[0] - vals[-1]) / vals[0] if vals[0] > 0 else 0.0
    if slope >= 0 or drop_frac < min_drop_frac:
        return None
    return AlertDraft(
        plant_id=plant_id, inverter_id=inverter_id, type="insulation_trend",
        severity=Severity.INVESTIGATE,
        recommended_action="Schedule insulation inspection before it trips on ground fault",
        confidence=0.7,
        risk_note="Early insulation degradation — Riso falling week-over-week (still above trip threshold).",
        evidence={"weekly_riso_kohm": list(vals), "slope_kohm_per_week": round(slope, 1),
                  "drop_pct": round(drop_frac * 100, 1)},
    )


def detect_arc_fault(plant_id: str, inverter_id: str, *, arc_fault_flag: bool | None) -> AlertDraft | None:
    if not arc_fault_flag:
        return None
    return AlertDraft(
        plant_id=plant_id, inverter_id=inverter_id, type="arc_fault",
        severity=Severity.CRITICAL,
        recommended_action="Dispatch immediately — arc fault detected",
        confidence=1.0,
        risk_note="FIRE RISK: DC arc fault flagged by the inverter. De-energize and inspect connectors.",
        evidence={"arc_fault_flag": True},
    )


def detect_open_or_degraded_string(
    plant_id: str, inverter_id: str, string_id: str,
    *, dc_current: float, dc_voltage: float, peer_deficit_frac: float,
    persistent: bool, recovered_on_cleaning: bool = False, clock_locked: bool = False,
    rated_share: float = 0.0, expected_kwh_window: float = 0.0, tariff_rate: float = 0.0,
) -> AlertDraft | None:
    """Split the string signal into an OPEN circuit vs a DEGRADED (resistive) string."""
    # OPEN: no current but voltage present AND peers are producing → a real broken
    # wire / connector / blown fuse. The peer check prevents a false "open" at dawn/
    # dusk/cloud, when ~0 current with voltage present is just low light, not a fault.
    if (dc_current <= OPEN_CURRENT_EPS_A and dc_voltage >= V_PRESENT_MIN
            and peer_deficit_frac >= OPEN_REL_DEFICIT):
        rs_day = round(rated_share * expected_kwh_window * tariff_rate, 2) or None
        return AlertDraft(
            plant_id=plant_id, inverter_id=inverter_id, string_id=string_id,
            type="string_open", severity=Severity.CRITICAL,
            recommended_action="Open circuit — check string fuse, connector, and wiring",
            confidence=0.95, rupee_impact_per_day=rs_day,
            risk_note="String producing no current with voltage present — broken conductor / blown fuse.",
            evidence={"dc_current": dc_current, "dc_voltage": dc_voltage},
        )
    # DEGRADED: persistently 8-25% low, not explained by cleaning recovery or shading.
    if (DEGRADED_LOW <= peer_deficit_frac <= DEGRADED_HIGH and persistent
            and not recovered_on_cleaning and not clock_locked):
        rs_day = round(peer_deficit_frac * rated_share * expected_kwh_window * tariff_rate, 2) or None
        return AlertDraft(
            plant_id=plant_id, inverter_id=inverter_id, string_id=string_id,
            type="string_degraded", severity=Severity.INVESTIGATE,
            recommended_action="Resistive/connector degradation — confirm on visit (runs hot)",
            confidence=0.65, rupee_impact_per_day=rs_day,
            risk_note="Series-resistance fault: a degraded connector runs hot — a thermal risk over time.",
            evidence={"peer_deficit_pct": round(peer_deficit_frac * 100, 1),
                      "persistent": persistent},
        )
    return None
