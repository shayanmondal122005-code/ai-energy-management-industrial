"""MicroGrid AI decision engine — runs every 15 minutes per facility.
6 rules: emergency charge, future low SoC, ToD cheap charging,
pre-charge for peak, peak-hour discharge, demand shave.
Physics and rule thresholds are correct — do not modify.
"""
from datetime import datetime
from typing import Any

from backend.services.battery_tracker import BatteryTracker

DEFAULT_RULES = {
    "soc_critical"      : 20,
    "soc_warning"       : 35,
    "soc_target_min"    : 50,
    "soc_target_max"    : 90,
    "hours_warning"     : 3,
    "hours_critical"    : 1,
    "peak_demand_kw"    : 350,
    "tod_cheap_hours"   : list(range(10, 16)),
    "tod_peak_hours"    : list(range(18, 23)),
    "precharge_threshold": 60,
}


class MicrogridBrain:
    def __init__(self, battery: BatteryTracker, rules: dict | None = None):
        self.battery = battery
        self.rules   = {**DEFAULT_RULES, **(rules or {})}

    def run(
        self,
        current_hour: int,
        current_load_kw: float,
        current_solar_kw: float,
        forecast_load: list[float],
        forecast_solar: list[float],
        temp_c: float = 30.0,
    ) -> dict[str, Any]:
        current_soc = self.battery.update(
            net_power_kw=current_solar_kw - current_load_kw,
            delta_hours=0.25,
            temp_c=temp_c,
        )
        future_soc     = self.battery.simulate_future(forecast_load, forecast_solar, temp_c=temp_c)
        hours_left     = self.battery.hours_remaining(current_load_kw, current_solar_kw)
        min_future_soc = min(future_soc)
        when_lowest    = future_soc.index(min_future_soc)

        is_cheap_now = current_hour in self.rules["tod_cheap_hours"]
        is_peak_now  = current_hour in self.rules["tod_peak_hours"]
        peak_coming  = any(h % 24 in self.rules["tod_peak_hours"] for h in range(current_hour, current_hour + 4))

        alerts, actions = [], []

        if current_soc < self.rules["soc_critical"]:
            alerts.append({
                "severity": "CRITICAL",
                "type"    : "BATTERY_CRITICAL",
                "message" : f"Battery at {current_soc:.0f}% — CRITICAL. Grid import required immediately.",
                "action"  : "CHARGE_NOW",
                "value"   : current_soc,
                "threshold": self.rules["soc_critical"],
            })
            actions.append("EMERGENCY_CHARGE")

        elif min_future_soc < self.rules["soc_critical"]:
            alerts.append({
                "severity": "WARNING",
                "type"    : "BATTERY_LOW_FORECAST",
                "message" : f"Battery forecast to reach {min_future_soc:.0f}% in {when_lowest}h. Plan grid charging.",
                "action"  : "PLAN_CHARGE",
                "value"   : min_future_soc,
                "threshold": self.rules["soc_critical"],
            })

        if is_cheap_now and current_soc < self.rules["precharge_threshold"] and not is_peak_now:
            actions.append("CHARGE_FROM_GRID")
            alerts.append({
                "severity": "INFO",
                "type"    : "TOD_CHEAP_CHARGING",
                "message" : f"Off-peak rate active. Charging battery from {current_soc:.0f}% to {self.rules['precharge_threshold']}%.",
                "action"  : "CHARGING",
                "value"   : current_soc,
            })

        if peak_coming and current_soc < self.rules["precharge_threshold"] and is_cheap_now and not is_peak_now:
            hours_until_peak = (self.rules["tod_peak_hours"][0] - current_hour) % 24
            actions.append("PRECHARGE_FOR_PEAK")
            alerts.append({
                "severity": "INFO",
                "type"    : "PRECHARGE",
                "message" : f"Peak in {hours_until_peak}h. Pre-charging at cheap rate now.",
                "action"  : "PRECHARGING",
                "value"   : current_soc,
            })

        if is_peak_now and current_soc > (self.rules["soc_critical"] + 10):
            actions.append("DISCHARGE_TO_SHAVE_PEAK")
            alerts.append({
                "severity": "INFO",
                "type"    : "PEAK_DISCHARGE",
                "message" : f"Peak tariff active. Discharging battery to cover {current_load_kw:.0f}kW load.",
                "action"  : "DISCHARGING",
                "value"   : current_soc,
            })

        if current_load_kw > self.rules["peak_demand_kw"] and current_soc > (self.rules["soc_critical"] + 5):
            shave = current_load_kw - self.rules["peak_demand_kw"]
            actions.append("DEMAND_SHAVE")
            alerts.append({
                "severity": "WARNING",
                "type"    : "DEMAND_PEAK",
                "message" : f"Demand {current_load_kw:.0f}kW above {self.rules['peak_demand_kw']}kW. Discharging {shave:.0f}kW to prevent demand charge.",
                "action"  : "SHAVING",
                "value"   : current_load_kw,
                "threshold": self.rules["peak_demand_kw"],
            })

        if not actions:
            actions.append("HOLD")

        return {
            "timestamp"       : datetime.utcnow().isoformat(),
            "current_soc_pct" : round(current_soc, 1),
            "hours_remaining" : hours_left,
            "min_future_soc"  : round(min_future_soc, 1),
            "lowest_in_hrs"   : when_lowest,
            "soh_pct"         : self.battery.soh_pct(),
            "actions"         : actions,
            "alerts"          : alerts,
            "is_cheap_tariff" : is_cheap_now,
            "is_peak_tariff"  : is_peak_now,
            "future_soc_trace": future_soc,
        }
