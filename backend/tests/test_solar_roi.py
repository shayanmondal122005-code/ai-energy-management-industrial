"""Tests for the solar ROI / payback tracker (and the lifted energy_kwh helper)."""
from datetime import datetime, timedelta, timezone

import math

from backend.services.solar_roi import energy_kwh, solar_payback


class TestEnergyKwh:
    def test_average_power_times_hours(self):
        t0 = datetime(2026, 6, 29, 6, 0, tzinfo=timezone.utc)
        t1 = t0 + timedelta(hours=10)
        # 120 kW average over 10 h = 1200 kWh
        assert energy_kwh(120.0, t0, t1) == 1200.0

    def test_none_inputs_zero(self):
        t0 = datetime(2026, 6, 29, tzinfo=timezone.utc)
        assert energy_kwh(None, t0, t0) == 0.0
        assert energy_kwh(100.0, None, t0) == 0.0
        assert energy_kwh(100.0, t0, None) == 0.0

    def test_degenerate_window_zero(self):
        t0 = datetime(2026, 6, 29, tzinfo=timezone.utc)
        assert energy_kwh(100.0, t0, t0) == 0.0  # zero span


class TestSolarPayback:
    def test_no_data(self):
        p = solar_payback(0, system_cost_rs=5_000_000, solar_value_per_kwh=6.10)
        assert p.status == "no_data"
        assert p.recovered_pct == 0.0
        assert p.remaining_rs == 5_000_000

    def test_partial_recovery(self):
        # 500,000 kWh at ₹6.10 = ₹3,050,000 of a ₹5,000,000 system → 61%.
        p = solar_payback(500_000, system_cost_rs=5_000_000, solar_value_per_kwh=6.10)
        assert p.status == "recovering"
        assert math.isclose(p.value_to_date_rs, 3_050_000, rel_tol=1e-6)
        assert math.isclose(p.recovered_pct, 61.0, abs_tol=0.1)
        assert math.isclose(p.remaining_rs, 1_950_000, rel_tol=1e-6)

    def test_recovered_pct_capped_at_100(self):
        p = solar_payback(2_000_000, system_cost_rs=5_000_000, solar_value_per_kwh=6.10)
        assert p.status == "paid_back"
        assert p.recovered_pct == 100.0
        assert p.remaining_rs == 0.0
        assert p.payback_eta_days is None  # nothing left to recover

    def test_eta_from_run_rate(self):
        # ₹1,950,000 remaining; 800 kWh/day at ₹6.10 = ₹4,880/day → ~400 days.
        p = solar_payback(
            500_000, system_cost_rs=5_000_000, solar_value_per_kwh=6.10,
            recent_daily_kwh=800,
        )
        assert p.daily_value_rs is not None
        assert math.isclose(p.daily_value_rs, 4_880.0, abs_tol=1.0)
        assert p.payback_eta_days == round(1_950_000 / 4_880)
        assert p.payback_eta_years is not None

    def test_no_eta_without_run_rate(self):
        p = solar_payback(500_000, system_cost_rs=5_000_000, solar_value_per_kwh=6.10)
        assert p.payback_eta_days is None
        assert p.daily_value_rs is None

    def test_co2_and_trees(self):
        # 500,000 kWh × 0.71 = 355,000 kg CO2; / 21 ≈ 16,905 trees-years.
        p = solar_payback(500_000, system_cost_rs=5_000_000, solar_value_per_kwh=6.10)
        assert math.isclose(p.co2_avoided_kg_total, 355_000.0, rel_tol=1e-6)
        assert p.trees_equivalent > 0
