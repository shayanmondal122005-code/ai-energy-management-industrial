"""Detector 3 — STRING / MPPT underperformance.

Compare a string's DC current to the MEDIAN of its peers on the same inverter at
the same interval (peers cancel out irradiance, so this needs no model):

  ratio = I_string / median(I_peers)
  fire when ratio < (1 − θ_string), θ_string = 0.08, sustained > N intervals
    8–15% low  → investigate
    >15% low   → investigate (note: likely open substring / blown fuse / diode)
  If the dip recurs at the SAME clock time every day → tag "likely shading", lower severity.
  ₹ = (median − I_string)/median × rated_share × expected_kwh × tariff

Every Tier-1 deviation is routed through environmental_gate by the caller FIRST;
a gate DOWNWEIGHT is folded in via `confidence_factor`, a SUPPRESS means this is
never called.
"""
from __future__ import annotations

import statistics

from backend.services.solar_om.detectors.base import rupee_per_day
from backend.services.solar_om.models import AlertDraft, Severity

THETA_STRING = 0.08
OPEN_LIKELY_DEFICIT = 0.15


def string_current_ratio(string_current: float, peer_currents: list[float]) -> float:
    """I_string / median(peers). Returns 1.0 if there are no peers (can't compare)."""
    peers = [c for c in peer_currents if c is not None]
    if not peers:
        return 1.0
    med = statistics.median(peers)
    if med <= 0:
        return 1.0
    return string_current / med


def detect_string_underperformance(
    plant_id: str, inverter_id: str, string_id: str,
    ratio_series: list[float],
    *, expected_kwh_window: float, rated_share: float, tariff_rate: float,
    clock_locked: bool = False, theta_string: float = THETA_STRING,
    n_intervals: int = 3, confidence_factor: float = 1.0,
) -> AlertDraft | None:
    """ratio_series = peer-current ratio per interval over the recent window."""
    deficits = [max(0.0, 1.0 - r) for r in ratio_series]
    low = [d for d in deficits if d >= theta_string]
    if len(low) < n_intervals:
        return None

    mean_deficit = sum(low) / len(low)
    rs_day = rupee_per_day(mean_deficit * rated_share, expected_kwh_window, tariff_rate)

    if clock_locked:
        severity = Severity.INFO
        note = "Dip recurs at the same clock time daily — likely SHADING, not a fault"
    elif mean_deficit >= OPEN_LIKELY_DEFICIT:
        severity = Severity.INVESTIGATE
        note = f"String {mean_deficit*100:.0f}% below peers — likely open substring / blown fuse / diode"
    else:
        severity = Severity.INVESTIGATE
        note = f"String {mean_deficit*100:.0f}% below peers — investigate connectors / module"

    return AlertDraft(
        plant_id=plant_id, inverter_id=inverter_id, string_id=string_id,
        type="string_underperformance", severity=severity,
        recommended_action=note,
        confidence=round(min(1.0, 0.6 + mean_deficit) * confidence_factor, 3),
        rupee_impact_per_day=rs_day,
        evidence={
            "mean_deficit_pct": round(mean_deficit * 100, 1),
            "intervals_low": len(low), "clock_locked": clock_locked,
            "rated_share": rated_share,
        },
    )


def is_clock_locked(low_hours_by_day: list[set[int]], *, min_days: int = 2) -> bool:
    """True if the under-performance recurs in the SAME hour(s) across multiple days
    (a shading fingerprint — a fault doesn't politely repeat at the same clock time)."""
    days = [h for h in low_hours_by_day if h]
    if len(days) < min_days:
        return False
    common = set.intersection(*days)
    return len(common) > 0
