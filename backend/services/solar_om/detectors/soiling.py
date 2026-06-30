"""Detector 1 — SOILING.

A gradual, UNIFORM decline of daily PR_tcorr across consecutive DRY days that
RECOVERS after rain or a `cleaning` event (that recovery, checked at verification,
is what distinguishes soiling from permanent degradation). Runs on DAILY PR, so it
is EXEMPT from the intraday environmental gate (clouds average out day-to-day).

  SR_pct_per_day = −slope(PR_tcorr) / mean(PR_tcorr) × 100    (dry-window decline rate)
  loss_pct       = SR_pct_per_day × days_since_clean          (cumulative vs clean)
  ₹/day          = loss_pct/100 × expected_kwh_day × ₹/kWh
  ₹ accumulated  = triangle integral over days_since_clean    (loss grew from ~0)
  → fire when loss_pct > θ_soil; recommend cleaning once ₹ accumulated ≥ cleaning cost.
"""
from __future__ import annotations

import numpy as np

from backend.services.solar_om.detectors.base import rupee_per_day
from backend.services.solar_om.models import AlertDraft, Severity

THETA_SOIL_DEFAULT_PCT = 5.0
THETA_SOIL_HIGH_VALUE_PCT = 3.0


def soiling_rate_pct_per_day(pr_tcorr_series: list[float]) -> float:
    """Decline rate of PR_tcorr over the dry window, as % of mean PR per day."""
    n = len(pr_tcorr_series)
    if n < 3:
        return 0.0
    x = np.arange(n, dtype=float)
    y = np.array(pr_tcorr_series, dtype=float)
    slope = float(np.polyfit(x, y, 1)[0])      # PR units per day (negative if soiling)
    mean_pr = float(y.mean())
    if mean_pr <= 0:
        return 0.0
    rate = -slope / mean_pr * 100.0
    return rate if rate > 1e-6 else 0.0   # clamp float dust on a flat series


def detect_soiling(
    plant_id: str,
    pr_tcorr_series: list[float],
    *,
    days_since_clean: int,
    expected_kwh_day: float,
    tariff_rate: float,
    cleaning_cost: float,
    uniform_across_strings: bool = True,
    theta_soil_pct: float = THETA_SOIL_DEFAULT_PCT,
) -> AlertDraft | None:
    """Return a soiling AlertDraft or None. `uniform_across_strings` must hold —
    a non-uniform decline is a string/MPPT fault, not soiling."""
    if not uniform_across_strings or days_since_clean <= 0:
        return None
    sr = soiling_rate_pct_per_day(pr_tcorr_series)
    if sr <= 0:
        return None
    loss_pct = sr * days_since_clean
    if loss_pct <= theta_soil_pct:
        return None

    loss_frac = loss_pct / 100.0
    rs_day = rupee_per_day(loss_frac, expected_kwh_day, tariff_rate)
    # Loss grew roughly linearly from ~0 since the last clean → triangle integral.
    rs_accumulated = round(0.5 * loss_frac * expected_kwh_day * tariff_rate * days_since_clean, 2)
    clean_now = rs_accumulated >= cleaning_cost
    action = (f"Clean panels now — ₹{rs_accumulated:.0f} lost ≥ ₹{cleaning_cost:.0f} cleaning cost"
              if clean_now else
              f"Soiling building (₹{rs_accumulated:.0f} lost so far); clean when it reaches "
              f"₹{cleaning_cost:.0f}")
    return AlertDraft(
        plant_id=plant_id, type="soiling",
        severity=Severity.INVESTIGATE if clean_now else Severity.INFO,
        recommended_action=action,
        confidence=min(1.0, 0.6 + 0.1 * (loss_pct - theta_soil_pct)),
        rupee_impact_per_day=rs_day, rupee_accumulated=rs_accumulated,
        evidence={
            "soiling_rate_pct_per_day": round(sr, 3),
            "loss_pct": round(loss_pct, 2),
            "days_since_clean": days_since_clean,
            "pr_tcorr_first": round(pr_tcorr_series[0], 4),
            "pr_tcorr_last": round(pr_tcorr_series[-1], 4),
            "cleaning_cost": cleaning_cost,
            "recommend_clean": clean_now,
        },
    )
