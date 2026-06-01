"""Tests for physics-based battery tracker."""
import pytest
from backend.services.battery_tracker import BatteryTracker


class TestBatteryTracker:
    def test_initial_soc(self):
        b = BatteryTracker({"capacity_kwh": 500, "initial_soc": 0.80})
        assert b.soc == 0.80

    def test_charging_increases_soc(self):
        b = BatteryTracker({"capacity_kwh": 500, "initial_soc": 0.50})
        soc = b.update(net_power_kw=100, delta_hours=1.0)
        assert soc > 50.0

    def test_discharging_decreases_soc(self):
        b = BatteryTracker({"capacity_kwh": 500, "initial_soc": 0.80})
        soc = b.update(net_power_kw=-100, delta_hours=1.0)
        assert soc < 80.0

    def test_soc_never_below_min(self):
        b = BatteryTracker({"capacity_kwh": 500, "initial_soc": 0.11, "min_soc": 0.10})
        for _ in range(20):
            b.update(net_power_kw=-500, delta_hours=1.0)
        assert b.soc >= 0.10

    def test_soc_never_above_max(self):
        b = BatteryTracker({"capacity_kwh": 500, "initial_soc": 0.94, "max_soc": 0.95})
        for _ in range(10):
            b.update(net_power_kw=200, delta_hours=1.0)
        assert b.soc <= 0.95

    def test_temperature_reduces_capacity(self):
        b_hot  = BatteryTracker({"capacity_kwh": 500, "initial_soc": 0.50, "temp_coefficient": 0.005})
        b_cold = BatteryTracker({"capacity_kwh": 500, "initial_soc": 0.50, "temp_coefficient": 0.005})
        soc_hot  = b_hot.update(100, delta_hours=1.0, temp_c=40)
        soc_cold = b_cold.update(100, delta_hours=1.0, temp_c=25)
        # Hot battery charges less efficiently
        assert soc_hot < soc_cold

    def test_hours_remaining_infinite_when_charging(self):
        b = BatteryTracker()
        b.soc = 0.70
        assert b.hours_remaining(load_kw=100, solar_kw=200) == float("inf")

    def test_soh_starts_at_100(self):
        b = BatteryTracker({"capacity_kwh": 500})
        assert b.soh_pct() == 100.0

    def test_simulate_future_returns_correct_length(self):
        b = BatteryTracker()
        b.soc = 0.70
        trace = b.simulate_future([300] * 24, [150] * 24)
        assert len(trace) == 25  # initial + 24 steps
