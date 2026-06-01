"""Physics-based battery State of Charge tracker.
Coulomb counting + Arrhenius temperature correction + degradation model.
Physics is correct — do not modify the equations.
"""
import numpy as np


DEFAULT_SPECS = {
    "capacity_kwh"        : 500,
    "max_charge_kw"       : 150,
    "max_discharge_kw"    : 200,
    "charge_efficiency"   : 0.95,
    "discharge_efficiency": 0.95,
    "min_soc"             : 0.10,
    "max_soc"             : 0.95,
    "initial_soc"         : 0.80,
    "degradation_rate"    : 0.00005,
    "temp_coefficient"    : 0.005,
}


class BatteryTracker:
    """Per-facility battery state tracker — instantiate one per facility."""

    def __init__(self, specs: dict | None = None):
        self.specs        = {**DEFAULT_SPECS, **(specs or {})}
        self.soc          = self.specs["initial_soc"]
        self.capacity_kwh = float(self.specs["capacity_kwh"])
        self.cycles       = 0.0

    def update(self, net_power_kw: float, delta_hours: float = 0.25, temp_c: float = 25.0) -> float:
        """Update SoC from net power over one time step. Returns SoC %."""
        temp_factor        = 1 - self.specs["temp_coefficient"] * max(0.0, temp_c - 25)
        effective_capacity = self.capacity_kwh * temp_factor

        if net_power_kw > 0:
            actual = min(net_power_kw, self.specs["max_charge_kw"])
            delta  = (actual * self.specs["charge_efficiency"] * delta_hours) / effective_capacity
        else:
            actual = max(net_power_kw, -self.specs["max_discharge_kw"])
            delta  = (actual / self.specs["discharge_efficiency"] * delta_hours) / effective_capacity
            self.cycles       += abs(delta) / 2
            self.capacity_kwh *= (1 - self.specs["degradation_rate"] * abs(delta))

        self.soc = float(np.clip(self.soc + delta, self.specs["min_soc"], self.specs["max_soc"]))
        return self.soc * 100

    def hours_remaining(self, load_kw: float, solar_kw: float) -> float:
        net = solar_kw - load_kw
        if net >= 0:
            return float("inf")
        usable    = (self.soc - self.specs["min_soc"]) * self.capacity_kwh
        drain_rate = abs(net) / self.specs["discharge_efficiency"]
        return round(usable / drain_rate, 1) if drain_rate > 0 else float("inf")

    def soh_pct(self) -> float:
        return round(self.capacity_kwh / self.specs["capacity_kwh"] * 100, 1)

    def simulate_future(
        self,
        forecast_load_kw: list[float],
        forecast_solar_kw: list[float],
        delta_hours: float = 1.0,
        temp_c: float = 30.0,
    ) -> list[float]:
        """Simulate SoC over N hours. Returns list of SoC% values."""
        sim_soc = self.soc
        sim_cap = self.capacity_kwh
        trace   = [round(sim_soc * 100, 1)]

        for load, solar in zip(forecast_load_kw, forecast_solar_kw):
            net = solar - load
            if net > 0:
                delta = (min(net, self.specs["max_charge_kw"])
                         * self.specs["charge_efficiency"] * delta_hours) / sim_cap
            else:
                delta = (max(net, -self.specs["max_discharge_kw"])
                         / self.specs["discharge_efficiency"] * delta_hours) / sim_cap
            sim_soc = float(np.clip(sim_soc + delta, self.specs["min_soc"], self.specs["max_soc"]))
            trace.append(round(sim_soc * 100, 1))

        return trace
