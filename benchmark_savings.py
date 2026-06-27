#!/usr/bin/env python3
"""Reproducible monthly savings benchmark for the MicroGrid AI cost optimizer.

Runs optimize_dispatch_v2 over a representative day for a mid-size Indian
hospital, scales to a month, and compares the WITH-EMS bill against a NO-EMS
baseline across all four levers: ToD energy arbitrage, peak-demand shaving,
power-factor correction, and battery wear. Writes benchmark_result.json.

All assumptions live in benchmark_config.json — edit there, not here.
Run:  python benchmark_savings.py
"""
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from backend.services.optimizer_v2 import optimize_dispatch_v2          # noqa: E402
from backend.services.pf_penalty import pf_penalty_from_tariff          # noqa: E402
from backend.services.alert_service import INDIA_TARIFFS                 # noqa: E402

CFG = json.load(open(os.path.join(ROOT, "benchmark_config.json")))


def tariff_schedule(state):
    """24h ₹/kWh schedule (hour 0..23) + the tariff dict for the state."""
    t = INDIA_TARIFFS[state]
    sched = []
    for h in range(24):
        if h in t["cheap_hours"]:
            sched.append(float(t["cheap"]))
        elif h in t["peak_hours"]:
            sched.append(float(t["peak"]))
        else:
            sched.append(float(t["normal"]))
    return sched, t


def load_profile(peak_kw, daily_kwh):
    """Representative 24h hospital load (flat-ish, evening peak), scaled to daily_kwh."""
    shape = [0.62, 0.60, 0.60, 0.61, 0.63, 0.66,   # 0-5  night
             0.74, 0.80, 0.85, 0.88, 0.90, 0.90,   # 6-11 morning/day
             0.92, 0.92, 0.91, 0.90, 0.92, 0.96,   # 12-17 afternoon
             1.00, 1.00, 0.98, 0.92, 0.78, 0.68]   # 18-23 evening peak
    raw = [peak_kw * s for s in shape]
    scale = daily_kwh / sum(raw)
    return [round(v * scale, 1) for v in raw]


def solar_profile(daily_kwh):
    """Representative 24h PV generation (midday bell), scaled to daily_kwh."""
    shape = [0, 0, 0, 0, 0, 0, 0.10, 0.30, 0.55, 0.78, 0.92, 0.99,
             1.0, 0.99, 0.92, 0.78, 0.55, 0.30, 0.10, 0, 0, 0, 0, 0]
    s = sum(shape)
    return [round(v / s * daily_kwh, 1) for v in shape]


def main():
    state = CFG["tariff_state"]
    sched, t = tariff_schedule(state)
    demand_per_kw = float(t["demand_per_kw"])
    days = CFG["days_in_month"]

    daily_kwh = CFG["monthly_consumption_kwh"] / days
    load = load_profile(CFG["peak_load_kw"], daily_kwh)
    solar = solar_profile(CFG["solar_daily_kwh"])

    # ── Baseline: NO EMS (solar passively offsets load; battery idle) ──
    base_grid = [max(0.0, load[h] - solar[h]) for h in range(24)]
    base_energy_month = sum(base_grid[h] * sched[h] for h in range(24)) * days
    base_peak = max(base_grid)
    base_demand_month = base_peak * demand_per_kw
    pf0 = CFG["assumed_power_factor"]
    base_pf = pf_penalty_from_tariff(pf0, base_energy_month + base_demand_month, t)
    baseline = base_energy_month + base_demand_month + base_pf

    # ── Optimized: WITH EMS dispatch ──
    eff = math.sqrt(CFG["round_trip_efficiency"])          # per-direction efficiency
    sanctioned_kw = CFG["sanctioned_demand_kva"] * pf0     # kVA -> kW at current PF
    s = optimize_dispatch_v2(
        load_forecast=load, solar_forecast=solar, tariff_schedule=sched,
        current_soc=0.5, battery_kwh=CFG["battery_kwh"],
        max_charge_kw=CFG["battery_inverter_kw"], max_discharge_kw=CFG["battery_inverter_kw"],
        charge_eff=eff, discharge_eff=eff,
        min_soc=CFG["soc_floor_pct"] / 100.0, max_soc=CFG["soc_ceiling_pct"] / 100.0,
        demand_charge_per_kw=demand_per_kw, safety_margin=0.0,
        max_grid_kw=sanctioned_kw,
    )
    opt_energy_month = s.cost_energy * days
    opt_demand_month = s.peak_grid_kw * demand_per_kw
    degr_month = s.cost_degradation * days
    opt_pf = pf_penalty_from_tariff(CFG["ems_corrects_pf_to"], opt_energy_month + opt_demand_month, t)
    optimized = opt_energy_month + opt_demand_month + degr_month + opt_pf

    savings = baseline - optimized
    breakdown = {
        "energy_arbitrage_inr": round(base_energy_month - opt_energy_month),
        "demand_shaving_inr":   round(base_demand_month - opt_demand_month),
        "pf_correction_inr":    round(base_pf - opt_pf),
        "battery_wear_inr":     round(-degr_month),
    }

    # ── Safety checks on the optimizer's recommendation ──
    viol = 0
    floor, ceil = CFG["soc_floor_pct"], CFG["soc_ceiling_pct"]
    if any(soc < floor - 0.5 or soc > ceil + 0.5 for soc in s.soc_trace):
        viol += 1
    if max(s.discharge_kw) > CFG["battery_inverter_kw"] + 0.5:
        viol += 1
    if max(s.charge_kw) > CFG["battery_inverter_kw"] + 0.5:
        viol += 1
    if max(s.grid_kw) > sanctioned_kw + 0.5:
        viol += 1
    if not s.status.startswith(("optimal", "fallback")):
        viol += 1

    target = CFG["target_monthly_savings_inr"]
    target_met = bool(savings >= target and viol == 0)

    result = {
        "monthly_savings_inr": round(savings),
        "baseline_inr": round(baseline),
        "optimized_inr": round(optimized),
        "target_inr": target,
        "target_met": target_met,
        "savings_breakdown_inr": breakdown,
        "safety_violations": viol,
        "optimizer_status": s.status,
        "assumptions": {
            **{k: v for k, v in CFG.items() if not k.startswith("_")},
            "tariff": {"cheap": t["cheap"], "normal": t["normal"], "peak": t["peak"],
                       "demand_per_kw": demand_per_kw,
                       "pf_threshold": t.get("pf_threshold"), "pf_penalty_pct": t.get("pf_penalty_pct")},
            "actual_monthly_load_kwh": round(sum(load) * days),
            "actual_daily_solar_kwh": round(sum(solar), 1),
            "baseline_peak_kw": round(base_peak, 1),
            "optimized_peak_kw": round(s.peak_grid_kw, 1),
        },
    }
    with open(os.path.join(ROOT, "benchmark_result.json"), "w") as f:
        json.dump(result, f, indent=2)

    print(f"Baseline:  Rs {baseline:>13,.0f} /month")
    print(f"Optimized: Rs {optimized:>13,.0f} /month")
    print(f"SAVINGS:   Rs {savings:>13,.0f} /month   (target Rs {target:,}) -> {'TARGET MET' if target_met else 'not met'}")
    print(f"  breakdown: {breakdown}")
    print(f"  safety_violations={viol}  optimizer_status={s.status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
