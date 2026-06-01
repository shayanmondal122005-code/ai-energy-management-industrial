"""Economic Dispatch Optimizer — Linear Programming.

Solves the 24-hour battery dispatch problem:
  Minimize:  total grid import cost
  Subject to: power balance every hour
              SoC never below 10% (no power cut — mathematically guaranteed)
              hardware limits (max charge/discharge rates)

Variables (97 total):
  g[0..23]  = grid import per hour (kW)
  c[0..23]  = battery charge per hour (kW)
  d[0..23]  = battery discharge per hour (kW)
  s[0..24]  = battery SoC per hour (fraction 0-1), 25 values (start + 24 end states)

Layout in flat vector x[0..96]:
  x[0..23]   = g
  x[24..47]  = c
  x[48..71]  = d
  x[72..96]  = s  (25 values)
"""
import logging
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

logger = logging.getLogger(__name__)

N = 24  # hours


@dataclass
class OptimalSchedule:
    """24-hour optimized dispatch schedule."""
    grid_kw:        list[float]   # grid import per hour
    charge_kw:      list[float]   # battery charge per hour
    discharge_kw:   list[float]   # battery discharge per hour
    soc_trace:      list[float]   # SoC % at each hour (25 values)
    cost_optimized: float         # total cost with optimizer (₹)
    cost_baseline:  float         # total cost without optimizer (₹)
    savings:        float         # ₹ saved today
    status:         str           # "optimal" | "infeasible" | "fallback"
    summary:        list[dict]    # hour-by-hour readable summary


def optimize_dispatch(
    load_forecast:    list[float],   # 24 values, kW
    solar_forecast:   list[float],   # 24 values, kW
    tariff_schedule:  list[float],   # 24 values, ₹/kWh
    current_soc:      float,         # 0.0 – 1.0
    battery_kwh:      float = 500.0,
    max_charge_kw:    float = 150.0,
    max_discharge_kw: float = 200.0,
    charge_eff:       float = 0.95,
    discharge_eff:    float = 0.95,
    min_soc:          float = 0.10,
    max_soc:          float = 0.95,
) -> OptimalSchedule:
    """
    Solve LP and return optimal battery schedule for next 24 hours.

    Variable index layout:
      g = x[0:N]        grid import
      c = x[N:2N]       battery charge
      d = x[2N:3N]      battery discharge
      s = x[3N:3N+N+1]  SoC (25 values: hour 0 through hour 24)
    """
    T   = N
    NV  = 3 * T + (T + 1)  # 97 total variables

    # ── Indices ──────────────────────────────────────────────
    g_idx = lambda h: h            # grid import
    c_idx = lambda h: T + h        # charge
    d_idx = lambda h: 2 * T + h    # discharge
    s_idx = lambda h: 3 * T + h    # SoC (h = 0..24)

    # ── Objective: minimise Σ g[h] × price[h] ───────────────
    obj = np.zeros(NV)
    for h in range(T):
        obj[g_idx(h)] = float(tariff_schedule[h])

    # ── Equality constraints ─────────────────────────────────
    # 1. Power balance every hour (T rows):
    #    g[h] + solar[h] + d[h] - c[h] = load[h]
    #    → g[h] + d[h] - c[h] = load[h] - solar[h]
    #
    # 2. SoC dynamics every hour (T rows):
    #    s[h+1] = s[h] + c[h]*η_c/cap - d[h]/(η_d*cap)
    #    → s[h+1] - s[h] - c[h]*η_c/cap + d[h]/(η_d*cap) = 0
    #
    # 3. Fix initial SoC (1 row):
    #    s[0] = current_soc
    #
    # Total: 2T + 1 = 49 equality rows

    n_eq = 2 * T + 1
    A_eq = np.zeros((n_eq, NV))
    b_eq = np.zeros(n_eq)

    # Power balance
    for h in range(T):
        A_eq[h, g_idx(h)] =  1.0
        A_eq[h, d_idx(h)] =  1.0
        A_eq[h, c_idx(h)] = -1.0
        b_eq[h]            = float(load_forecast[h]) - float(solar_forecast[h])

    # SoC dynamics
    for h in range(T):
        row = T + h
        A_eq[row, s_idx(h + 1)] =  1.0
        A_eq[row, s_idx(h)]     = -1.0
        A_eq[row, c_idx(h)]     = -(charge_eff / battery_kwh)
        A_eq[row, d_idx(h)]     =  1.0 / (discharge_eff * battery_kwh)
        b_eq[row]               =  0.0

    # Fix initial SoC
    A_eq[2 * T, s_idx(0)] = 1.0
    b_eq[2 * T]           = float(current_soc)

    # ── Variable bounds ──────────────────────────────────────
    bounds = []
    for h in range(T):
        bounds.append((0.0, None))              # g[h] >= 0
    for h in range(T):
        bounds.append((0.0, max_charge_kw))     # 0 <= c[h] <= max_charge
    for h in range(T):
        bounds.append((0.0, max_discharge_kw))  # 0 <= d[h] <= max_discharge
    for h in range(T + 1):
        bounds.append((min_soc, max_soc))       # min_soc <= s[h] <= max_soc

    # ── Solve ────────────────────────────────────────────────
    result = linprog(
        c=obj,
        A_eq=A_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",   # HiGHS solver — fast, reliable
        options={"disp": False},
    )

    if result.status != 0:
        logger.warning("LP infeasible (status=%d) — falling back to rules", result.status)
        return _fallback_schedule(
            load_forecast, solar_forecast, tariff_schedule,
            current_soc, battery_kwh, charge_eff, discharge_eff,
            min_soc, max_soc, max_charge_kw, max_discharge_kw,
        )

    x = result.x
    grid_kw      = [max(0.0, round(x[g_idx(h)], 1)) for h in range(T)]
    charge_kw    = [max(0.0, round(x[c_idx(h)], 1)) for h in range(T)]
    discharge_kw = [max(0.0, round(x[d_idx(h)], 1)) for h in range(T)]
    soc_trace    = [round(x[s_idx(h)] * 100, 1) for h in range(T + 1)]

    cost_opt  = sum(grid_kw[h] * tariff_schedule[h] for h in range(T))
    cost_base = sum(max(0.0, load_forecast[h] - solar_forecast[h]) * tariff_schedule[h] for h in range(T))
    savings   = round(cost_base - cost_opt, 0)

    summary = _build_summary(grid_kw, charge_kw, discharge_kw, soc_trace,
                              load_forecast, solar_forecast, tariff_schedule)

    logger.info("Optimizer: cost=₹%.0f baseline=₹%.0f saved=₹%.0f", cost_opt, cost_base, savings)

    return OptimalSchedule(
        grid_kw=grid_kw,
        charge_kw=charge_kw,
        discharge_kw=discharge_kw,
        soc_trace=soc_trace,
        cost_optimized=round(cost_opt, 0),
        cost_baseline=round(cost_base, 0),
        savings=savings,
        status="optimal",
        summary=summary,
    )


def _build_summary(grid, charge, discharge, soc, load, solar, price) -> list[dict]:
    rows = []
    for h in range(N):
        if charge[h] > 1:
            action = "CHARGE"
        elif discharge[h] > 1:
            action = "DISCHARGE"
        else:
            action = "HOLD"

        period = "cheap" if price[h] <= 4.5 else "peak" if price[h] >= 7.0 else "normal"

        rows.append({
            "hour"        : h,
            "load_kw"     : round(load[h], 0),
            "solar_kw"    : round(solar[h], 0),
            "grid_kw"     : round(grid[h], 0),
            "charge_kw"   : round(charge[h], 0),
            "discharge_kw": round(discharge[h], 0),
            "soc_pct"     : soc[h],
            "action"      : action,
            "tariff"      : price[h],
            "period"      : period,
            "cost_inr"    : round(grid[h] * price[h], 0),
        })
    return rows


def _fallback_schedule(
    load, solar, price, current_soc,
    battery_kwh, charge_eff, discharge_eff,
    min_soc, max_soc, max_charge_kw, max_discharge_kw,
) -> OptimalSchedule:
    """
    Rule-based fallback when LP is infeasible
    (e.g. battery too small to cover load gap).
    Runs original 6-rule brain logic hour by hour.
    """
    soc   = float(current_soc)
    grid, charge, discharge, soc_trace = [], [], [], [round(soc * 100, 1)]

    cheap_hours = [h for h in range(N) if price[h] <= 4.5]
    peak_hours  = [h for h in range(N) if price[h] >= 7.0]

    for h in range(N):
        net_solar = solar[h] - load[h]  # positive = surplus
        is_cheap  = h in cheap_hours
        is_peak   = h in peak_hours
        peak_soon = any((h + k) % 24 in peak_hours for k in range(1, 5))

        c, d = 0.0, 0.0

        if net_solar > 0:
            # Solar surplus — charge battery
            c = min(net_solar, max_charge_kw, (max_soc - soc) * battery_kwh / charge_eff)
            c = max(0.0, c)

        elif is_cheap and soc < 0.75 and not is_peak:
            # Cheap rate — charge from grid
            c = min(max_charge_kw, (0.80 - soc) * battery_kwh / charge_eff)
            c = max(0.0, c)

        elif is_peak and soc > min_soc + 0.15:
            # Peak rate — discharge battery
            d = min(max_discharge_kw, load[h] - solar[h], (soc - min_soc - 0.05) * battery_kwh * discharge_eff)
            d = max(0.0, d)

        # Power balance
        covered = solar[h] + d - c
        g = max(0.0, load[h] - covered)

        # Update SoC
        soc += (c * charge_eff - d / discharge_eff) / battery_kwh
        soc  = float(np.clip(soc, min_soc, max_soc))

        grid.append(round(g, 1))
        charge.append(round(c, 1))
        discharge.append(round(d, 1))
        soc_trace.append(round(soc * 100, 1))

    cost_opt  = sum(grid[h] * price[h] for h in range(N))
    cost_base = sum(max(0.0, load[h] - solar[h]) * price[h] for h in range(N))

    summary = _build_summary(grid, charge, discharge, soc_trace, load, solar, price)

    return OptimalSchedule(
        grid_kw=grid, charge_kw=charge, discharge_kw=discharge,
        soc_trace=soc_trace,
        cost_optimized=round(cost_opt, 0),
        cost_baseline=round(cost_base, 0),
        savings=round(cost_base - cost_opt, 0),
        status="fallback",
        summary=summary,
    )


def get_current_hour_command(schedule: OptimalSchedule, hour: int) -> str:
    """Read what battery should do RIGHT NOW from the stored schedule."""
    if hour >= N:
        return "HOLD"
    c = schedule.charge_kw[hour]
    d = schedule.discharge_kw[hour]
    if c > 1.0:
        return "CHARGE"
    if d > 1.0:
        return "DISCHARGE"
    return "HOLD"
