"""Economic Dispatch Optimizer V2 — Absolute Minimum Cost.

Upgrades over V1:
  1. DEMAND CHARGE minimization — flattens peak grid draw (₹/kW)
     Often the biggest single saving for hospitals (30-40% of bill)
  2. BATTERY DEGRADATION cost — stops uneconomic cycling, extends battery life
  3. GRID CHARGING in cheap hours — explicitly fills battery from grid when
     solar is insufficient and tariff is low, then discharges at peak
  4. ROBUST SAFETY MARGIN — buffers against load forecast error

Full objective (still a fast Linear Program, ~50ms):

  minimize:  Σ grid[h] × price[h]                    ← energy cost
           + demand_charge × peak_excess              ← demand charge (NEW)
           + degradation × Σ discharge[h]             ← battery wear, per kWh discharged

  subject to:
    load[h] = solar[h] + grid[h] + discharge[h] - charge[h]   (power balance)
    soc[h+1] = soc[h] + charge[h]×ηc/cap - discharge[h]/(ηd×cap)
    peak_excess ≥ grid[h] - month_peak_so_far    for all h    (demand linearization)
    soc[h] ≥ min_soc + safety_margin             for all h    (no power cut + buffer)
    soc[h] ≤ max_soc
    grid[h], charge[h], discharge[h] ≥ 0

Variable layout in flat vector x:
  g[0..23]   grid import       indices 0..N-1
  c[0..23]   battery charge    indices N..2N-1
  d[0..23]   battery discharge indices 2N..3N-1
  s[0..24]   SoC               indices 3N..4N
  peak_excess                  index 4N+1  (single scalar)
"""
import logging
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linprog

logger = logging.getLogger(__name__)

N = 24  # hours

# ── Economic constants (tune per customer) ───────────────────
# LiFePO4: 6000 cycles, ₹8000/kWh, 80% DoD
#   degradation = 8000 / (6000 × 0.8) = ₹1.67 per kWh throughput
DEFAULT_DEGRADATION_COST = 1.67   # ₹ per kWh charged or discharged
DEFAULT_SAFETY_MARGIN    = 0.05   # keep 5% SoC buffer above min for forecast error


@dataclass
class OptimalScheduleV2:
    grid_kw:         list[float]
    charge_kw:       list[float]
    discharge_kw:    list[float]
    soc_trace:       list[float]
    peak_grid_kw:    float
    cost_energy:     float          # ₹ — energy charge only
    cost_demand:     float          # ₹ — demand charge for the day
    cost_degradation:float          # ₹ — battery wear cost
    cost_total:      float          # ₹ — everything
    cost_baseline:   float          # ₹ — no optimization (grid follows load)
    savings:         float          # ₹ saved vs baseline
    grid_charge_kwh: float          # how much battery charged FROM GRID (cheap)
    solar_charge_kwh:float          # how much battery charged from solar
    status:          str
    summary:         list[dict] = field(default_factory=list)
    # Solar spill accounting — excess solar that on-site load + battery couldn't absorb.
    solar_spilled_kwh:   float = 0.0  # total excess solar (exported + curtailed)
    solar_exported_kwh:  float = 0.0  # spill sold to grid (only if export_allowed)
    solar_curtailed_kwh: float = 0.0  # spill wasted (no export path) — pure loss
    export_value_rs:     float = 0.0  # ₹ earned from exported spill


def optimize_dispatch_v2(
    load_forecast:    list[float],
    solar_forecast:   list[float],
    tariff_schedule:  list[float],
    current_soc:      float,
    battery_kwh:      float = 500.0,
    max_charge_kw:    float = 150.0,
    max_discharge_kw: float = 200.0,
    charge_eff:       float = 0.95,
    discharge_eff:    float = 0.95,
    min_soc:          float = 0.10,
    max_soc:          float = 0.95,
    demand_charge_per_kw: float = 320.0,   # ₹/kW/month (CESC default)
    month_peak_so_far_kw: float = 0.0,     # month-to-date peak grid draw
    degradation_cost: float = DEFAULT_DEGRADATION_COST,
    safety_margin:    float = DEFAULT_SAFETY_MARGIN,
    export_rate:      float = 0.0,     # ₹/kWh paid for solar exported to grid
    export_allowed:   bool  = False,   # GATED: most India C&I has no/zero export — default off
) -> OptimalScheduleV2:
    """
    Solve the full cost-minimization LP and return optimal schedule.

    The solver automatically decides whether to charge the battery from
    solar surplus OR cheap grid import — whichever minimizes total cost.

    A solar SPILL variable absorbs excess solar that on-site load + battery can't
    take, so a high-solar day can never be infeasible. By default spill is
    CURTAILED (wasted, no value); only when export_allowed AND export_rate>0 is
    spill credited as export revenue — we don't assume a feed-in tariff that the
    connection may not have.
    """
    T  = N
    eff_export_rate = float(export_rate) if export_allowed else 0.0
    # Variables: g[T] + c[T] + d[T] + spill[T] + s[T+1] + peak_excess[1]
    NV = 4 * T + (T + 1) + 1
    PEAK_IDX = 4 * T + (T + 1)   # index of peak_excess scalar

    g_idx = lambda h: h
    c_idx = lambda h: T + h
    d_idx = lambda h: 2 * T + h
    e_idx = lambda h: 3 * T + h        # solar spill (export or curtail)
    s_idx = lambda h: 4 * T + h

    # Amortize monthly demand charge to this single day (÷30)
    demand_daily = demand_charge_per_kw / 30.0

    # ── Objective ────────────────────────────────────────────
    obj = np.zeros(NV)
    for h in range(T):
        obj[g_idx(h)] = float(tariff_schedule[h])         # energy cost
        # Battery wear: ₹1.67/kWh is the per-kWh-DISCHARGED cycle cost
        # (8000 / (6000 × 0.8)). Penalising charge AND discharge double-counts
        # a single charge→discharge cycle and wrongly kills economic arbitrage.
        obj[d_idx(h)] = degradation_cost                  # wear per kWh discharged
        # Exported spill earns revenue → negative cost. Curtailed spill (default)
        # has 0 coefficient: free to dump, but no value — so the LP still prefers
        # self-consumption and battery storage over wasting solar.
        obj[e_idx(h)] = -eff_export_rate
    obj[PEAK_IDX] = demand_daily                          # demand charge

    # ── Equality constraints: power balance + SoC dynamics + initial SoC ──
    n_eq = 2 * T + 1
    A_eq = np.zeros((n_eq, NV))
    b_eq = np.zeros(n_eq)

    for h in range(T):
        # load = solar + grid + discharge - charge - spill
        #   → grid + discharge - charge - spill = load - solar
        A_eq[h, g_idx(h)] =  1.0
        A_eq[h, d_idx(h)] =  1.0
        A_eq[h, c_idx(h)] = -1.0
        A_eq[h, e_idx(h)] = -1.0          # spill absorbs excess solar → always feasible
        b_eq[h] = float(load_forecast[h]) - float(solar_forecast[h])

    for h in range(T):
        row = T + h
        A_eq[row, s_idx(h + 1)] =  1.0
        A_eq[row, s_idx(h)]     = -1.0
        A_eq[row, c_idx(h)]     = -(charge_eff / battery_kwh)
        A_eq[row, d_idx(h)]     =  1.0 / (discharge_eff * battery_kwh)

    A_eq[2 * T, s_idx(0)] = 1.0
    b_eq[2 * T]           = float(current_soc)

    # ── Inequality: peak_excess ≥ grid[h] - month_peak_so_far ──
    # Rewritten: grid[h] - peak_excess ≤ month_peak_so_far
    n_ub = T
    A_ub = np.zeros((n_ub, NV))
    b_ub = np.zeros(n_ub)
    for h in range(T):
        A_ub[h, g_idx(h)]   =  1.0
        A_ub[h, PEAK_IDX]   = -1.0
        b_ub[h] = float(month_peak_so_far_kw)

    # ── Bounds ───────────────────────────────────────────────
    eff_min_soc = min(min_soc + safety_margin, max_soc - 0.01)
    bounds = []
    for h in range(T):
        bounds.append((0.0, None))                 # grid ≥ 0
    for h in range(T):
        bounds.append((0.0, max_charge_kw))        # charge
    for h in range(T):
        bounds.append((0.0, max_discharge_kw))     # discharge
    for h in range(T):
        # spill ≤ this hour's solar (can't dump more solar than is generated)
        bounds.append((0.0, max(0.0, float(solar_forecast[h]))))   # solar spill
    # Terminal SoC must not end below the starting SoC. Otherwise the optimizer
    # "saves" money by permanently draining pre-stored energy — not a real or
    # sustainable daily saving. This makes daily cycling honest and comparable.
    terminal_floor = min(max(current_soc, eff_min_soc), max_soc - 0.01)
    for h in range(T + 1):
        lo = terminal_floor if h == T else eff_min_soc
        bounds.append((lo, max_soc))               # SoC with safety buffer
    bounds.append((0.0, None))                     # peak_excess ≥ 0

    # ── Solve ────────────────────────────────────────────────
    result = linprog(
        c=obj, A_eq=A_eq, b_eq=b_eq, A_ub=A_ub, b_ub=b_ub,
        bounds=bounds, method="highs", options={"disp": False},
    )

    if result.status != 0:
        # Infeasible — relax safety margin and retry once
        logger.warning("V2 LP infeasible (status=%d) — retrying without safety margin", result.status)
        if safety_margin > 0:
            return optimize_dispatch_v2(
                load_forecast, solar_forecast, tariff_schedule, current_soc,
                battery_kwh, max_charge_kw, max_discharge_kw, charge_eff, discharge_eff,
                min_soc, max_soc, demand_charge_per_kw, month_peak_so_far_kw,
                degradation_cost, safety_margin=0.0,
                export_rate=export_rate, export_allowed=export_allowed,
            )
        return _fallback_v2(load_forecast, solar_forecast, tariff_schedule, current_soc,
                            battery_kwh, demand_charge_per_kw)

    x = result.x
    grid_kw      = [max(0.0, round(x[g_idx(h)], 1)) for h in range(T)]
    charge_kw    = [max(0.0, round(x[c_idx(h)], 1)) for h in range(T)]
    discharge_kw = [max(0.0, round(x[d_idx(h)], 1)) for h in range(T)]
    spill_kw     = [max(0.0, round(x[e_idx(h)], 1)) for h in range(T)]
    soc_trace    = [round(x[s_idx(h)] * 100, 1) for h in range(T + 1)]
    peak_excess  = max(0.0, x[PEAK_IDX])
    peak_grid    = max(grid_kw)

    # ── Solar spill accounting (exported vs curtailed) ───────
    solar_spilled_kwh = sum(spill_kw)
    if eff_export_rate > 0:
        solar_exported_kwh  = solar_spilled_kwh
        solar_curtailed_kwh = 0.0
        export_value_rs     = solar_spilled_kwh * eff_export_rate
    else:
        solar_exported_kwh  = 0.0
        solar_curtailed_kwh = solar_spilled_kwh   # no export path → pure loss
        export_value_rs     = 0.0

    # ── Cost breakdown ───────────────────────────────────────
    cost_energy = sum(grid_kw[h] * tariff_schedule[h] for h in range(T))
    cost_demand = peak_excess * demand_daily
    cost_degr   = degradation_cost * sum(discharge_kw[h] for h in range(T))
    cost_total  = cost_energy + cost_demand + cost_degr - export_value_rs

    # Baseline: no battery, grid follows net load, peak unmanaged
    base_grid   = [max(0.0, load_forecast[h] - solar_forecast[h]) for h in range(T)]
    cost_base_energy = sum(base_grid[h] * tariff_schedule[h] for h in range(T))
    base_peak_excess = max(0.0, max(base_grid) - month_peak_so_far_kw)
    cost_base_demand = base_peak_excess * demand_daily
    cost_baseline    = cost_base_energy + cost_base_demand

    savings = round(cost_baseline - cost_total, 0)

    # ── How much battery charged from grid vs solar ──────────
    grid_charge_kwh  = 0.0
    solar_charge_kwh = 0.0
    for h in range(T):
        solar_surplus = max(0.0, solar_forecast[h] - load_forecast[h])
        from_solar    = min(charge_kw[h], solar_surplus)
        from_grid     = charge_kw[h] - from_solar
        solar_charge_kwh += from_solar
        grid_charge_kwh  += from_grid

    summary = _build_summary_v2(grid_kw, charge_kw, discharge_kw, soc_trace,
                                load_forecast, solar_forecast, tariff_schedule, peak_grid)

    logger.info(
        "Optimizer V2: total=₹%.0f (energy=₹%.0f demand=₹%.0f wear=₹%.0f) saved=₹%.0f peak=%.0fkW",
        cost_total, cost_energy, cost_demand, cost_degr, savings, peak_grid,
    )

    return OptimalScheduleV2(
        grid_kw=grid_kw, charge_kw=charge_kw, discharge_kw=discharge_kw,
        soc_trace=soc_trace, peak_grid_kw=round(peak_grid, 1),
        cost_energy=round(cost_energy, 0), cost_demand=round(cost_demand, 0),
        cost_degradation=round(cost_degr, 0), cost_total=round(cost_total, 0),
        cost_baseline=round(cost_baseline, 0), savings=savings,
        grid_charge_kwh=round(grid_charge_kwh, 1),
        solar_charge_kwh=round(solar_charge_kwh, 1),
        status="optimal", summary=summary,
        solar_spilled_kwh=round(solar_spilled_kwh, 1),
        solar_exported_kwh=round(solar_exported_kwh, 1),
        solar_curtailed_kwh=round(solar_curtailed_kwh, 1),
        export_value_rs=round(export_value_rs, 0),
    )


def _build_summary_v2(grid, charge, discharge, soc, load, solar, price, peak) -> list[dict]:
    rows = []
    for h in range(N):
        if charge[h] > 1:
            # Determine charge source
            solar_surplus = max(0.0, solar[h] - load[h])
            action = "CHARGE_SOLAR" if charge[h] <= solar_surplus + 1 else "CHARGE_GRID"
        elif discharge[h] > 1:
            action = "DISCHARGE"
        else:
            action = "HOLD"
        period = "cheap" if price[h] <= 4.5 else "peak" if price[h] >= 7.0 else "normal"
        rows.append({
            "hour": h, "load_kw": round(load[h], 0), "solar_kw": round(solar[h], 0),
            "grid_kw": round(grid[h], 0), "charge_kw": round(charge[h], 0),
            "discharge_kw": round(discharge[h], 0), "soc_pct": soc[h],
            "action": action, "tariff": price[h], "period": period,
            "cost_inr": round(grid[h] * price[h], 0),
            "is_peak_draw": round(grid[h], 0) >= round(peak, 0) - 1,
        })
    return rows


def _fallback_v2(load, solar, price, current_soc, battery_kwh, demand_charge) -> OptimalScheduleV2:
    """Conservative grid-only fallback if LP fails entirely."""
    grid = [max(0.0, load[h] - solar[h]) for h in range(N)]
    soc  = [round(current_soc * 100, 1)] * (N + 1)
    cost = sum(grid[h] * price[h] for h in range(N))
    summary = _build_summary_v2(grid, [0]*N, [0]*N, soc, load, solar, price, max(grid))
    return OptimalScheduleV2(
        grid_kw=grid, charge_kw=[0]*N, discharge_kw=[0]*N, soc_trace=soc,
        peak_grid_kw=round(max(grid), 1),
        cost_energy=round(cost, 0), cost_demand=0, cost_degradation=0,
        cost_total=round(cost, 0), cost_baseline=round(cost, 0), savings=0,
        grid_charge_kwh=0, solar_charge_kwh=0, status="fallback", summary=summary,
    )


def get_current_hour_command_v2(schedule: OptimalScheduleV2, hour: int) -> str:
    """Return CHARGE / DISCHARGE / HOLD for the current hour."""
    if hour >= N:
        return "HOLD"
    if schedule.charge_kw[hour] > 1.0:
        return "CHARGE"
    if schedule.discharge_kw[hour] > 1.0:
        return "DISCHARGE"
    return "HOLD"
