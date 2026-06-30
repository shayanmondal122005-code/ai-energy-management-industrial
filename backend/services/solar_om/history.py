"""EMS history integration — a SECOND, data-driven 'expected' from the site's own trend.

The detector's primary baseline is PHYSICS-expected (satellite POA → model). The EMS
brings months of this site's actual generation, which gives a complementary
DATA-EXPECTED: the site's own measured clean-day Performance Ratio. Using it:

  • `site_baseline_pr`  — the site's true clean baseline PR (robust to soiled days),
    a data-driven yardstick that captures real shading / orientation / module reality
    the physics model can't know.
  • `calibrate_eta_bos_from_history` — fit eta_bos over the EMS's accumulated clean,
    clear-sky days instead of waiting out a 2-4 week commissioning window.
  • `baseline_deviation` — how far today sits below the site's OWN normal; agreement
    between this and the physics deviation is the highest-confidence dip signal.

All pure functions — the EMS supplies the history arrays; no coupling to its service.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from backend.services.solar_om.baseline import calibrate_eta_bos, expected_power_w, performance_ratio
from backend.services.solar_om.forecast import derive_variability
from backend.services.solar_om.irradiance import clearsky_ghi
from backend.services.solar_om.models import Plant


def _clean_clearsky(daily_pr: list[float], clear_sky: list[bool]) -> list[float]:
    return [pr for pr, cs in zip(daily_pr, clear_sky) if cs and pr > 0]


def site_baseline_pr(daily_pr_tcorr: list[float], clear_sky_flags: list[bool],
                     *, min_days: int = 10, percentile: float = 75.0) -> float | None:
    """The site's clean-baseline PR_tcorr from its own history.

    Uses a high percentile of CLEAR-SKY days so accumulated soiling on dirty days does
    not drag the baseline down — we want 'as good as this site gets when clean'. Returns
    None until there are enough clear-sky days to trust.
    """
    clean = _clean_clearsky(daily_pr_tcorr, clear_sky_flags)
    if len(clean) < min_days:
        return None
    return round(float(np.percentile(clean, percentile)), 4)


def calibrate_eta_bos_from_history(
    plant: Plant, daily_actual_kwh: list[float], daily_ideal_kwh: list[float],
    clear_sky_flags: list[bool], *, min_days: int = 10,
) -> float | None:
    """Fit eta_bos over the EMS's clean, clear-sky days (vs a 2-4 week fresh window)."""
    a, i = [], []
    for act, ideal, cs in zip(daily_actual_kwh, daily_ideal_kwh, clear_sky_flags):
        if cs and ideal > 0:
            a.append(act)
            i.append(ideal)
    if len(a) < min_days:
        return None
    return calibrate_eta_bos(plant, a, i)


def compute_daily_calibration(plant: Plant, hourly_rows, env_source, *, clearsky_fn=clearsky_ghi):
    """Roll an hourly solar history into per-day calibration inputs.

    `hourly_rows` is any sequence of objects with `.hr` (timestamp) and `.solar_kw`
    (the hour's average AC kW) — e.g. the EMS readings_hourly rollup. For each day it
    returns aligned lists: (actual_kWh, ideal_kWh at eta=1 from modeled POA, PR_tcorr,
    clear_sky_flag). Pure — the env + clear-sky are injected, so it unit-tests.
    """
    by_day: dict = defaultdict(list)
    for r in hourly_rows:
        ts = r.hr
        by_day[ts.date()].append((ts, float(getattr(r, "solar_kw", 0.0) or 0.0)))

    actual_kwh, ideal_kwh, pr_tcorr, clear = [], [], [], []
    for _day, hours in sorted(by_day.items()):
        envs = [env_source.get(plant, ts) for ts, _ in hours]
        a_kwh = sum(kw for _, kw in hours)                                  # hourly kW ≈ kWh
        i_kwh = sum(expected_power_w(plant, e, eta_bos=1.0) for e in envs) / 1000.0
        pr = performance_ratio(plant, a_kwh, envs, 1.0)
        clearness = []
        for (ts, _), e in zip(hours, envs):
            cs = clearsky_fn(ts, plant.lat, plant.lon)
            if cs > 50.0:
                clearness.append(max(0.0, e.ghi_wm2) / cs)
        _, is_clear = derive_variability(clearness)
        actual_kwh.append(a_kwh)
        ideal_kwh.append(i_kwh)
        pr_tcorr.append(pr.pr_tcorr)
        clear.append(is_clear)
    return actual_kwh, ideal_kwh, pr_tcorr, clear


def calibrate_from_hourly(plant: Plant, hourly_rows, env_source, *, min_days: int = 10,
                          clearsky_fn=clearsky_ghi) -> tuple[float | None, float | None]:
    """End-to-end: hourly history → (eta_bos, baseline_pr) over clean clear-sky days.
    Returns (None, None) until there are enough clear days to trust."""
    a, i, p, c = compute_daily_calibration(plant, hourly_rows, env_source, clearsky_fn=clearsky_fn)
    eta = calibrate_eta_bos_from_history(plant, a, i, c, min_days=min_days)
    base = site_baseline_pr(p, c, min_days=min_days)
    return eta, base


def baseline_deviation(today_pr_tcorr: float, baseline_pr: float) -> float:
    """Fraction below the site's OWN clean baseline (data-driven anomaly). 0 if at/above."""
    if baseline_pr <= 0:
        return 0.0
    return max(0.0, (baseline_pr - today_pr_tcorr) / baseline_pr)


def corroborated_loss(physics_deviation: float, data_deviation: float,
                      *, agree_tol: float = 0.03) -> tuple[float, float]:
    """Blend the physics-expected deviation with the EMS data-expected deviation.

    Returns (loss_fraction, confidence). When the two baselines AGREE the dip is real
    and confidence is high; when they disagree we take the smaller (conservative) loss
    and lower confidence — a model artefact shouldn't raise a false alarm on its own.
    """
    agree = abs(physics_deviation - data_deviation) <= agree_tol
    if agree:
        return round((physics_deviation + data_deviation) / 2, 4), 0.95
    return round(min(physics_deviation, data_deviation), 4), 0.6
