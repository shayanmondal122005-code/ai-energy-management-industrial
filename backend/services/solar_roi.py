"""Solar ROI / payback tracker — the "protect your investment" number.

A solar array is a large up-front capex that pays itself back through years of
self-consumed energy. This module turns the cumulative generation we already
track (``readings_repo.get_solar_generation``) into the investor-facing view:
how much of the system cost the panels have earned back, how much is left, and —
at the current run rate — when it crosses break-even.

HONEST FRAMING — value is the energy the panels self-consume, priced at the
NORMAL grid rate they offset (not peak, no export-premium assumptions). We
measure what the array has produced; we do not assume a sunnier future. The ETA
is a straight-line projection from the recent run rate and is labelled as such.

Two pure helpers also live here:
  • ``energy_kwh`` — average-power × time-span → kWh, the core of the (previously
    untested) get_solar_generation aggregation, lifted out so it unit-tests.
  • ``solar_payback`` — the ROI rollup.

Pure functions — no DB/framework — so they unit-test without a database.
"""
from dataclasses import dataclass
from datetime import datetime

# India grid emission factor (CEA) — matches readings_repo.GRID_CO2_KG_PER_KWH.
GRID_CO2_KG_PER_KWH = 0.71
# A mature tree sequesters ~21 kg CO2/year (commonly cited) — for a relatable figure.
CO2_KG_PER_TREE_YEAR = 21.0


def energy_kwh(avg_kw: float | None, min_ts: datetime | None, max_ts: datetime | None) -> float:
    """Energy (kWh) over a window = average power (kW) × elapsed hours.

    This is the exact calculation get_solar_generation runs per window; lifted to a
    pure function so it is unit-testable (the SQL itself only runs against Postgres).
    Returns 0 for an empty/degenerate window.
    """
    if avg_kw is None or min_ts is None or max_ts is None:
        return 0.0
    hours = (max_ts - min_ts).total_seconds() / 3600.0
    if hours <= 0:
        return 0.0
    return round(float(avg_kw) * hours, 1)


@dataclass
class SolarPayback:
    total_kwh: float                 # lifetime solar generated (measured)
    system_cost_rs: float            # installed capex of the array
    value_to_date_rs: float          # ₹ of grid energy the array has offset so far
    recovered_pct: float             # % of capex earned back (capped at 100)
    remaining_rs: float              # ₹ of capex still to recover
    co2_avoided_kg_total: float      # lifetime CO2 avoided
    trees_equivalent: float          # relatable framing for the CO2
    daily_value_rs: float | None     # recent ₹/day run rate (drives the ETA)
    payback_eta_days: int | None     # straight-line days to break-even
    payback_eta_years: float | None  # same, in years
    status: str                      # "paid_back" | "recovering" | "no_data"


def solar_payback(
    total_kwh: float,
    system_cost_rs: float,
    solar_value_per_kwh: float,
    *,
    recent_daily_kwh: float | None = None,
    grid_co2_kg_per_kwh: float = GRID_CO2_KG_PER_KWH,
) -> SolarPayback:
    """Roll cumulative generation into a payback view.

    total_kwh           : lifetime solar kWh (from get_solar_generation.total_kwh).
    system_cost_rs      : what the array cost installed.
    solar_value_per_kwh : ₹ per self-consumed kWh = the normal grid rate it offsets.
    recent_daily_kwh    : recent kWh/day (e.g. month_kwh / days_elapsed) for the ETA.
                          If None, no ETA is projected (we don't guess a run rate).
    """
    total_kwh = max(0.0, float(total_kwh))
    system_cost_rs = max(0.0, float(system_cost_rs))
    rate = max(0.0, float(solar_value_per_kwh))

    value_to_date = round(total_kwh * rate, 2)
    co2_total = round(total_kwh * grid_co2_kg_per_kwh, 1)
    trees = round(co2_total / CO2_KG_PER_TREE_YEAR, 1) if CO2_KG_PER_TREE_YEAR else 0.0

    if total_kwh <= 0:
        return SolarPayback(
            total_kwh=0.0, system_cost_rs=system_cost_rs, value_to_date_rs=0.0,
            recovered_pct=0.0, remaining_rs=round(system_cost_rs, 2),
            co2_avoided_kg_total=0.0, trees_equivalent=0.0,
            daily_value_rs=None, payback_eta_days=None, payback_eta_years=None,
            status="no_data",
        )

    recovered_pct = round(min(100.0, value_to_date / system_cost_rs * 100), 1) if system_cost_rs > 0 else 100.0
    remaining = round(max(0.0, system_cost_rs - value_to_date), 2)

    daily_value = None
    eta_days = None
    eta_years = None
    if recent_daily_kwh is not None and recent_daily_kwh > 0 and rate > 0:
        daily_value = round(recent_daily_kwh * rate, 2)
        if remaining > 0 and daily_value > 0:
            eta_days = int(round(remaining / daily_value))
            eta_years = round(eta_days / 365.0, 2)

    status = "paid_back" if remaining <= 0 else "recovering"
    return SolarPayback(
        total_kwh=round(total_kwh, 1), system_cost_rs=round(system_cost_rs, 2),
        value_to_date_rs=value_to_date, recovered_pct=recovered_pct,
        remaining_rs=remaining, co2_avoided_kg_total=co2_total, trees_equivalent=trees,
        daily_value_rs=daily_value, payback_eta_days=eta_days, payback_eta_years=eta_years,
        status=status,
    )
