"""Tests for optimizer V2 — demand charge, degradation, grid charging."""
import numpy as np
from backend.services.optimizer_v2 import optimize_dispatch_v2


# CESC tariff: cheap 10-15h, peak 18-22h
def _cesc_price():
    return [7.85 if 18 <= h <= 22 else 4.20 if 10 <= h <= 15 else 6.10 for h in range(24)]


class TestOptimizerV2:

    def test_charges_from_grid_when_solar_insufficient_and_cheap(self):
        """Core requirement: charge battery from cheap grid when solar is weak.

        demand_charge is 0 here to isolate pure energy-cost arbitrage. With a real
        demand charge, grid-charging a flat load would create a NEW, higher demand
        peak that can outweigh the arbitrage — that (correct) interaction is covered
        by test_demand_charge_flattens_peak.
        """
        # Zero solar all day, but cheap tariff window exists
        s = optimize_dispatch_v2(
            load_forecast=[200.0] * 24,
            solar_forecast=[0.0] * 24,          # NO solar at all
            tariff_schedule=_cesc_price(),
            current_soc=0.30,
            battery_kwh=500,
            demand_charge_per_kw=0.0,
        )
        # Battery MUST have charged from grid during cheap hours
        assert s.grid_charge_kwh > 0, "Should charge battery from grid when solar is zero"
        cheap_charge = sum(s.charge_kw[h] for h in range(10, 16))
        assert cheap_charge > 0, "Should charge during cheap tariff hours"

    def test_demand_charge_flattens_peak(self):
        """With demand charge, peak grid draw should be lower than baseline."""
        load = [250 + 200 * (1 if 18 <= h <= 21 else 0) for h in range(24)]  # evening spike
        s = optimize_dispatch_v2(
            load_forecast=load,
            solar_forecast=[0.0] * 24,
            tariff_schedule=_cesc_price(),
            current_soc=0.80,
            battery_kwh=500,
            demand_charge_per_kw=320,
        )
        baseline_peak = max(load)
        assert s.peak_grid_kw < baseline_peak, "Demand charge should reduce peak grid draw"

    def test_degradation_prevents_tiny_arbitrage(self):
        """Battery should NOT cycle when spread < degradation cost."""
        # Flat-ish price — spread below ₹1.67 degradation cost
        flat_price = [6.0 if h < 12 else 6.5 for h in range(24)]  # spread only ₹0.50
        s = optimize_dispatch_v2(
            load_forecast=[200.0] * 24,
            solar_forecast=[0.0] * 24,
            tariff_schedule=flat_price,
            current_soc=0.50,
            battery_kwh=500,
            degradation_cost=1.67,
        )
        total_cycling = sum(s.charge_kw) + sum(s.discharge_kw)
        assert total_cycling < 100, "Should barely cycle when spread < degradation cost"

    def test_uses_solar_before_grid_for_charging(self):
        """When solar surplus exists, prefer it over grid for charging."""
        solar = [max(0, 250 * np.sin((h - 6) * np.pi / 12)) if 6 <= h <= 18 else 0 for h in range(24)]
        s = optimize_dispatch_v2(
            load_forecast=[150.0] * 24,
            solar_forecast=solar,
            tariff_schedule=_cesc_price(),
            current_soc=0.40,
            battery_kwh=500,
        )
        # Solar charging should happen when there's surplus
        assert s.solar_charge_kwh > 0, "Should charge from solar surplus"

    def test_soc_never_below_min(self):
        s = optimize_dispatch_v2(
            load_forecast=[400.0] * 24, solar_forecast=[0.0] * 24,
            tariff_schedule=_cesc_price(), current_soc=0.70, battery_kwh=500,
        )
        assert min(s.soc_trace) >= 9.0

    def test_power_balance_holds(self):
        solar = [max(0, 180 * np.sin((h - 6) * np.pi / 12)) if 6 <= h <= 18 else 0 for h in range(24)]
        load  = [300.0] * 24
        s = optimize_dispatch_v2(
            load_forecast=load, solar_forecast=solar,
            tariff_schedule=_cesc_price(), current_soc=0.70, battery_kwh=500,
        )
        for h in range(24):
            supplied = solar[h] + s.grid_kw[h] + s.discharge_kw[h] - s.charge_kw[h]
            assert abs(supplied - load[h]) < 1.5, f"Hour {h}: imbalance"

    def test_total_cost_breakdown_adds_up(self):
        s = optimize_dispatch_v2(
            load_forecast=[300.0] * 24,
            solar_forecast=[0.0] * 24,
            tariff_schedule=_cesc_price(),
            current_soc=0.70, battery_kwh=500,
        )
        recomputed = s.cost_energy + s.cost_demand + s.cost_degradation
        assert abs(recomputed - s.cost_total) < 1.0

    def test_v2_beats_baseline(self):
        solar = [max(0, 180 * np.sin((h - 6) * np.pi / 12)) if 6 <= h <= 18 else 0 for h in range(24)]
        s = optimize_dispatch_v2(
            load_forecast=[350.0] * 24, solar_forecast=solar,
            tariff_schedule=_cesc_price(), current_soc=0.70,
            battery_kwh=500, demand_charge_per_kw=320,
        )
        assert s.cost_total <= s.cost_baseline
        assert s.savings >= 0


class TestSolarCurtailmentExport:
    """The spill variable: a high-solar day must never be infeasible; excess solar is
    curtailed by default and only credited as export when explicitly allowed."""

    # Tiny, nearly-full battery + huge solar → most solar cannot be used or stored.
    _HIGH_SOLAR = dict(
        load_forecast=[100.0] * 24,
        solar_forecast=[600.0] * 24,   # 500 kW/h surplus, far beyond load + charge
        tariff_schedule=_cesc_price(),
        current_soc=0.90,              # almost full
        battery_kwh=100,               # small
        max_charge_kw=50,              # can soak at most 50 kW/h
        max_soc=0.95,
    )

    def test_high_solar_is_feasible_not_fallback(self):
        # Without a spill variable this LP is infeasible (charge ≥ 500 but cap 50).
        s = optimize_dispatch_v2(**self._HIGH_SOLAR)
        assert s.status == "optimal"
        assert s.solar_spilled_kwh > 0

    def test_default_spill_is_curtailed_not_exported(self):
        s = optimize_dispatch_v2(**self._HIGH_SOLAR)
        assert s.solar_curtailed_kwh > 0
        assert s.solar_exported_kwh == 0.0
        assert s.export_value_rs == 0.0

    def test_export_credited_only_when_allowed(self):
        s = optimize_dispatch_v2(**self._HIGH_SOLAR, export_allowed=True, export_rate=3.0)
        assert s.solar_exported_kwh > 0
        assert s.solar_curtailed_kwh == 0.0
        assert s.export_value_rs > 0

    def test_export_lowers_total_cost(self):
        curtail = optimize_dispatch_v2(**self._HIGH_SOLAR)
        export  = optimize_dispatch_v2(**self._HIGH_SOLAR, export_allowed=True, export_rate=3.0)
        # Selling the same spilled solar can only reduce (or equal) total cost.
        assert export.cost_total <= curtail.cost_total

    def test_export_rate_ignored_without_allowed_flag(self):
        # Passing a rate but not the flag must NOT credit export (gated).
        s = optimize_dispatch_v2(**self._HIGH_SOLAR, export_rate=3.0, export_allowed=False)
        assert s.export_value_rs == 0.0
        assert s.solar_exported_kwh == 0.0

    def test_prefers_storing_over_spilling_when_economic(self):
        # Midday solar surplus + an expensive evening peak with NO solar gives the
        # battery a real reason to store: charge cheap/free midday, discharge at peak.
        # The optimizer should store that surplus rather than spill all of it.
        solar = [200.0 if 10 <= h <= 15 else 0.0 for h in range(24)]   # 100 kW/h midday surplus
        load  = [100.0 + (250.0 if 18 <= h <= 22 else 0.0) for h in range(24)]  # evening peak
        s = optimize_dispatch_v2(
            load_forecast=load, solar_forecast=solar,
            tariff_schedule=_cesc_price(),
            current_soc=0.30, battery_kwh=500, max_charge_kw=150,
        )
        assert s.solar_charge_kwh > 0
        assert s.solar_charge_kwh > s.solar_spilled_kwh
