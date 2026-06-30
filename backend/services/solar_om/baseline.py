"""Baseline engine — weather-normalized EXPECTED generation, PR, and PR_tcorr.

Irradiance is MODELED (satellite/forecast), never sensed on site. Everything a
detector compares against — and every ₹ number — flows from here.

Physics (no irradiance/temp sensor on site):
    t_cell        = ambient + (poa/800) * (noct - 20)             # NOCT cell-temp model
    temp_factor   = 1 + gamma_P * (t_cell - 25)                   # Pmax temperature derate
    expected_W    = rated_kwp*1000 * (poa/1000) * temp_factor * eta_bos
    PR (daily)    = Σ ac_energy_kwh / (rated_kwp * daily_POA_insolation_kWh/m²)
    PR_tcorr      = PR / mean(temp_factor)   # remove the thermal handicap → isolates
                                             #   soiling/faults; use for DETECTION
                                             #   (raw PR for REPORTING)

A worked example is asserted in tests/test_baseline.py so the math is pinned.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.services.solar_om.models import EnvSample, Plant

STC_IRRADIANCE = 1000.0   # W/m²
NOCT_REF_IRRADIANCE = 800.0


def cell_temperature(ambient_temp_c: float, poa_wm2: float, noct_c: float) -> float:
    """NOCT model: cell runs hotter than air in proportion to irradiance."""
    return ambient_temp_c + (max(0.0, poa_wm2) / NOCT_REF_IRRADIANCE) * (noct_c - 20.0)


def temp_factor(plant: Plant, t_cell_c: float) -> float:
    """Pmax temperature derate (≈1 at 25 °C, <1 when hot). Floored at 0."""
    return max(0.0, 1.0 + plant.module_temp_coeff * (t_cell_c - 25.0))


def expected_power_w(plant: Plant, env: EnvSample, eta_bos: float | None = None) -> float:
    """Instantaneous expected AC power for the WHOLE plant under this env sample."""
    eta = plant.eta_bos if eta_bos is None else eta_bos
    if eta is None:
        eta = 1.0  # uncalibrated: report a raw physical ceiling (alerts suppressed elsewhere)
    if env.poa_wm2 <= 0:
        return 0.0
    t_cell = cell_temperature(env.ambient_temp_c, env.poa_wm2, plant.noct_c)
    tf = temp_factor(plant, t_cell)
    return plant.rated_capacity_kwp * 1000.0 * (env.poa_wm2 / STC_IRRADIANCE) * tf * eta


def expected_energy_kwh(plant: Plant, env_samples: list[EnvSample],
                        interval_hours: float, *, share: float = 1.0,
                        eta_bos: float | None = None) -> float:
    """Expected energy over a set of intervals (each `interval_hours` long).

    `share` scales to a sub-unit (inverter/string) by its rated fraction of the plant.
    Used by every detector and all ₹ math.
    """
    total_w = sum(expected_power_w(plant, e, eta_bos) for e in env_samples)
    return total_w / 1000.0 * interval_hours * share


def poa_insolation_kwh(env_samples: list[EnvSample], interval_hours: float) -> float:
    """Daily POA insolation in kWh/m² = Σ POA(W/m²)/1000 × hours."""
    return sum(max(0.0, e.poa_wm2) for e in env_samples) / 1000.0 * interval_hours


@dataclass(frozen=True)
class PRResult:
    pr: float           # raw Performance Ratio (for REPORTING)
    pr_tcorr: float     # temperature-corrected PR (for DETECTION)
    mean_temp_factor: float
    actual_kwh: float
    insolation_kwh_m2: float


def performance_ratio(plant: Plant, actual_kwh: float,
                      env_samples: list[EnvSample], interval_hours: float) -> PRResult:
    """Daily PR and PR_tcorr from measured energy + modeled POA/temperature."""
    insol = poa_insolation_kwh(env_samples, interval_hours)
    if insol <= 0 or plant.rated_capacity_kwp <= 0:
        return PRResult(0.0, 0.0, 1.0, actual_kwh, insol)
    pr = actual_kwh / (plant.rated_capacity_kwp * insol)
    # POA-weighted mean temp factor: thermal handicap is felt most when sun is strong.
    weights = np.array([max(0.0, e.poa_wm2) for e in env_samples], dtype=float)
    tcs = np.array([temp_factor(plant, cell_temperature(e.ambient_temp_c, e.poa_wm2, plant.noct_c))
                    for e in env_samples], dtype=float)
    mean_tf = float(np.average(tcs, weights=weights)) if weights.sum() > 0 else 1.0
    pr_tcorr = pr / mean_tf if mean_tf > 0 else pr
    return PRResult(pr=pr, pr_tcorr=pr_tcorr, mean_temp_factor=mean_tf,
                    actual_kwh=actual_kwh, insolation_kwh_m2=insol)


def calibrate_eta_bos(plant: Plant, daily_actual_kwh: list[float],
                      daily_ideal_kwh: list[float]) -> float | None:
    """Least-squares (through-origin) fit of eta_bos over a commissioning window.

    Caller passes only CLEAN, CLEAR-SKY, FAULT-FREE days (selected via
    ForecastProvider.clear_sky_flag). eta_bos = Σ(actual·ideal) / Σ(ideal²), where
    `ideal` is expected energy at eta_bos=1. Returns None if there is no signal.
    """
    a = np.array(daily_actual_kwh, dtype=float)
    i = np.array(daily_ideal_kwh, dtype=float)
    denom = float(np.dot(i, i))
    if denom <= 0 or len(a) == 0:
        return None
    eta = float(np.dot(a, i) / denom)
    return round(min(max(eta, 0.0), 1.0), 4)
