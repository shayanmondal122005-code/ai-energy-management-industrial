"""Baseline engine — PR math pinned to a HAND-CHECKED worked example.

Worked example (do the arithmetic by hand to trust the engine):
  rated_kwp = 100, poa = 800 W/m², ambient = 30 °C, noct = 45, gamma_P = -0.0035, eta_bos = 0.85
    t_cell      = 30 + (800/800)*(45-20)          = 55 °C
    temp_factor = 1 + (-0.0035)*(55-25)           = 1 - 0.105 = 0.895
    expected_W  = 100*1000 * (800/1000) * 0.895 * 0.85
                = 100000 * 0.8 * 0.895 * 0.85      = 60,860 W

Daily PR example (12 intervals of 1 h at the above, actual = 500 kWh):
    insolation  = 12 * 800/1000                    = 9.6 kWh/m²
    PR          = 500 / (100 * 9.6)                = 0.52083…
    PR_tcorr    = PR / 0.895                        = 0.58194…
"""
import math
from datetime import datetime, timedelta, timezone

from backend.services.solar_om.baseline import (
    calibrate_eta_bos,
    cell_temperature,
    expected_power_w,
    performance_ratio,
    temp_factor,
)
from backend.services.solar_om.models import EnvSample, EnvSource, Plant

IST = timezone(timedelta(hours=5, minutes=30))


def _plant(eta_bos=0.85):
    return Plant(id="PLANT-001", name="Test", lat=22.57, lon=88.36,
                 tilt_deg=22.0, azimuth_deg=180.0, rated_capacity_kwp=100.0,
                 module_temp_coeff=-0.0035, noct_c=45.0, eta_bos=eta_bos)


def _env(poa=800.0, ambient=30.0, h=10):
    return EnvSample(ts=datetime(2026, 6, 29, h, 0, tzinfo=IST), plant_id="PLANT-001",
                     poa_wm2=poa, ambient_temp_c=ambient, ghi_wm2=poa * 0.9,
                     source=EnvSource.SATELLITE)


class TestCellTempAndDerate:
    def test_cell_temperature(self):
        assert math.isclose(cell_temperature(30.0, 800.0, 45.0), 55.0, abs_tol=1e-9)

    def test_temp_factor(self):
        assert math.isclose(temp_factor(_plant(), 55.0), 0.895, abs_tol=1e-9)


class TestExpectedPower:
    def test_hand_checked_expected_power(self):
        p = expected_power_w(_plant(eta_bos=0.85), _env(poa=800.0, ambient=30.0))
        assert math.isclose(p, 60_860.0, abs_tol=1.0)

    def test_zero_at_night(self):
        assert expected_power_w(_plant(), _env(poa=0.0)) == 0.0


class TestPerformanceRatio:
    def test_hand_checked_pr_and_tcorr(self):
        envs = [_env(poa=800.0, ambient=30.0, h=h) for h in range(8, 20)]  # 12 intervals
        res = performance_ratio(_plant(), actual_kwh=500.0, env_samples=envs, interval_hours=1.0)
        assert math.isclose(res.insolation_kwh_m2, 9.6, abs_tol=1e-6)
        assert math.isclose(res.pr, 0.520833, abs_tol=1e-4)
        assert math.isclose(res.mean_temp_factor, 0.895, abs_tol=1e-4)
        assert math.isclose(res.pr_tcorr, 0.520833 / 0.895, abs_tol=1e-4)
        # PR_tcorr removes the thermal handicap → strictly higher than raw PR when hot.
        assert res.pr_tcorr > res.pr

    def test_no_insolation_is_safe(self):
        envs = [_env(poa=0.0, h=h) for h in range(0, 5)]
        res = performance_ratio(_plant(), actual_kwh=0.0, env_samples=envs, interval_hours=1.0)
        assert res.pr == 0.0 and res.pr_tcorr == 0.0


class TestCalibration:
    def test_eta_bos_recovered_from_clean_days(self):
        # If actual = 0.83 * ideal on every clean day, the fit must recover 0.83.
        ideal = [600.0, 580.0, 610.0, 595.0]
        actual = [0.83 * x for x in ideal]
        assert math.isclose(calibrate_eta_bos(_plant(), actual, ideal), 0.83, abs_tol=1e-3)

    def test_no_data_returns_none(self):
        assert calibrate_eta_bos(_plant(), [], []) is None
