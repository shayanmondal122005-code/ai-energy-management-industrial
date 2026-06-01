"""Tests for LP optimizer — critical correctness checks."""
import pytest
import numpy as np
from backend.services.optimizer import optimize_dispatch, get_current_hour_command


def _flat_scenario(load=300, solar=0, price=6.1, soc=0.70):
    """Simple flat 24h scenario."""
    return optimize_dispatch(
        load_forecast   =[load]  * 24,
        solar_forecast  =[solar] * 24,
        tariff_schedule =[price] * 24,
        current_soc     =soc,
        battery_kwh     =500,
        max_charge_kw   =150,
        max_discharge_kw=200,
    )


class TestOptimizerCorrectness:

    def test_returns_24_hour_schedule(self):
        s = _flat_scenario()
        assert len(s.grid_kw)      == 24
        assert len(s.charge_kw)    == 24
        assert len(s.discharge_kw) == 24
        assert len(s.soc_trace)    == 25  # start + 24 end states

    def test_soc_never_below_min(self):
        """Core guarantee: SoC must stay >= 10% at all hours."""
        s = _flat_scenario(load=400, solar=0, soc=0.68)
        assert min(s.soc_trace) >= 9.5, f"SoC dropped to {min(s.soc_trace):.1f}%"

    def test_soc_never_above_max(self):
        s = _flat_scenario(load=100, solar=200, soc=0.50)
        assert max(s.soc_trace) <= 96.0, f"SoC exceeded {max(s.soc_trace):.1f}%"

    def test_power_balance_every_hour(self):
        """Solar + grid + discharge - charge must equal load each hour."""
        solar = [max(0, 180 * np.sin((h - 6) * np.pi / 12)) if 6 <= h <= 18 else 0 for h in range(24)]
        load  = [300.0] * 24
        s = optimize_dispatch(
            load_forecast=load, solar_forecast=solar,
            tariff_schedule=[6.1] * 24, current_soc=0.70,
        )
        for h in range(24):
            supplied = solar[h] + s.grid_kw[h] + s.discharge_kw[h] - s.charge_kw[h]
            assert abs(supplied - load[h]) < 1.0, f"Hour {h}: power imbalance {supplied:.1f} vs {load[h]}"

    def test_charges_during_cheap_not_peak(self):
        """Optimizer should charge during cheap hours (₹4.2) not peak (₹7.85)."""
        price = [7.85 if 18 <= h <= 22 else 4.20 if 10 <= h <= 15 else 6.10 for h in range(24)]
        s = optimize_dispatch(
            load_forecast=[200.0] * 24, solar_forecast=[0.0] * 24,
            tariff_schedule=price, current_soc=0.30,
        )
        cheap_charge = sum(s.charge_kw[h] for h in range(10, 16))
        peak_charge  = sum(s.charge_kw[h] for h in range(18, 23))
        assert cheap_charge > peak_charge, "Should charge more during cheap hours than peak hours"

    def test_discharges_during_peak(self):
        """During peak hours, battery should discharge to avoid expensive grid import."""
        price = [7.85 if 18 <= h <= 22 else 4.20 if 10 <= h <= 15 else 6.10 for h in range(24)]
        s = optimize_dispatch(
            load_forecast=[400.0] * 24, solar_forecast=[0.0] * 24,
            tariff_schedule=price, current_soc=0.90,
        )
        peak_discharge = sum(s.discharge_kw[h] for h in range(18, 23))
        off_discharge  = sum(s.discharge_kw[h] for h in range(0, 8))
        assert peak_discharge > off_discharge, "Should discharge more during peak hours"

    def test_optimized_cost_less_than_baseline(self):
        """Optimizer must always find a cheaper solution than no optimization."""
        solar = [max(0, 180 * np.sin((h - 6) * np.pi / 12)) if 6 <= h <= 18 else 0 for h in range(24)]
        price = [7.85 if 18 <= h <= 22 else 4.20 if 10 <= h <= 15 else 6.10 for h in range(24)]
        s = optimize_dispatch(
            load_forecast=[350.0] * 24, solar_forecast=solar,
            tariff_schedule=price, current_soc=0.70,
        )
        assert s.cost_optimized <= s.cost_baseline, "Optimizer cost must be ≤ baseline"
        assert s.savings >= 0, "Savings must be non-negative"

    def test_get_current_hour_command(self):
        s = _flat_scenario()
        cmd = get_current_hour_command(s, hour=12)
        assert cmd in ("CHARGE", "DISCHARGE", "HOLD")

    def test_status_is_optimal_or_fallback(self):
        s = _flat_scenario()
        assert s.status in ("optimal", "fallback")

    def test_infeasible_returns_fallback_not_exception(self):
        """When LP can't solve, should return fallback schedule not raise."""
        s = optimize_dispatch(
            load_forecast   =[10000.0] * 24,  # impossible load
            solar_forecast  =[0.0] * 24,
            tariff_schedule =[6.1] * 24,
            current_soc     =0.10,
            battery_kwh     =10,              # tiny battery
            max_charge_kw   =5,
            max_discharge_kw=5,
        )
        assert s is not None
        assert s.status in ("optimal", "fallback")
