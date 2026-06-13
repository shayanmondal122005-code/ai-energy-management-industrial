"""Shadow-savings — realized savings from REAL history, not projections.

Replays each past day's actual load + solar through the dispatch optimizer and
sums the per-day savings (cost_baseline − cost_total). This is the honest,
defensible number to show a prospect: "over the last N days of YOUR data,
MicroGrid AI would have saved ₹X" — the core of the shadow-mode pilot.

Pure function over hourly rows so it unit-tests without a database.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from backend.services.alert_service import INDIA_TARIFFS
from backend.services.optimizer_v2 import optimize_dispatch_v2

# A day needs at least this many distinct hours of data to be evaluated —
# avoids counting partial days (e.g. the meter came online at noon).
MIN_HOURS_PER_DAY = 20


@dataclass
class ShadowSavings:
    total_savings_rs:     float
    days_evaluated:       int
    avg_daily_rs:         float
    projected_monthly_rs: float
    projected_annual_rs:  float
    daily:                list[dict] = field(default_factory=list)
    status:               str = "ok"   # "ok" | "insufficient_data"


def _tariff_for_day(state_tariff: str) -> tuple[list[float], float]:
    """24h tariff (hour 0..23) + demand charge for a calendar day."""
    t = INDIA_TARIFFS.get(state_tariff, INDIA_TARIFFS["West Bengal - CESC"])
    schedule = []
    for h in range(24):
        if h in t["cheap_hours"]:
            schedule.append(float(t["cheap"]))
        elif h in t["peak_hours"]:
            schedule.append(float(t["peak"]))
        else:
            schedule.append(float(t["normal"]))
    return schedule, float(t["demand_per_kw"])


def _fill_24h(hours: dict[int, tuple[float, float, float | None]]) -> tuple[list[float], list[float], float]:
    """Build dense 24h load/solar arrays + starting SoC from a sparse hour->(load,solar,soc) map.
    Missing hours are forward-then-backward filled so a one-hour gap doesn't void a day."""
    load: list[float | None] = [None] * 24
    solar: list[float | None] = [None] * 24
    for h, (l, s, _soc) in hours.items():
        load[h], solar[h] = l, s

    def densify(arr: list[float | None]) -> list[float]:
        last = None
        for h in range(24):                       # forward fill
            if arr[h] is not None:
                last = arr[h]
            elif last is not None:
                arr[h] = last
        last = None
        for h in range(23, -1, -1):               # backward fill leading gaps
            if arr[h] is not None:
                last = arr[h]
            elif last is not None:
                arr[h] = last
        return [float(x) if x is not None else 0.0 for x in arr]

    socs = [hours[h][2] for h in sorted(hours) if hours[h][2] is not None]
    start_soc = (float(socs[0]) / 100.0) if socs else 0.5
    start_soc = min(max(start_soc, 0.15), 0.9)    # clamp into a sane operating band
    return densify(load), densify(solar), start_soc


def compute_shadow_savings(
    hourly_rows,
    *,
    state_tariff: str,
    battery_kwh: float,
    min_hours_per_day: int = MIN_HOURS_PER_DAY,
) -> ShadowSavings:
    """hourly_rows: iterable of (timestamp: datetime, load_kw, solar_kw, soc_pct_or_None),
    one row per hour. Groups by calendar day, runs the optimizer per full day, sums savings."""
    by_day: dict[object, dict[int, tuple[float, float, float | None]]] = defaultdict(dict)
    for ts, load_kw, solar_kw, soc in hourly_rows:
        if not isinstance(ts, datetime):
            continue
        by_day[ts.date()][ts.hour] = (float(load_kw), float(solar_kw or 0.0), soc)

    tariff_schedule, demand_charge = _tariff_for_day(state_tariff)

    daily: list[dict] = []
    total = 0.0
    for day in sorted(by_day):
        hours = by_day[day]
        if len(hours) < min_hours_per_day:
            continue
        load, solar, start_soc = _fill_24h(hours)
        s = optimize_dispatch_v2(
            load_forecast=load,
            solar_forecast=solar,
            tariff_schedule=tariff_schedule,
            current_soc=start_soc,
            battery_kwh=battery_kwh,
            demand_charge_per_kw=demand_charge,
        )
        savings = max(0.0, float(s.savings))      # never report negative shadow savings
        total += savings
        daily.append({
            "date":         day.isoformat(),
            "savings_rs":   round(savings, 0),
            "baseline_rs":  round(float(s.cost_baseline), 0),
            "optimized_rs": round(float(s.cost_total), 0),
        })

    n = len(daily)
    if n == 0:
        return ShadowSavings(0.0, 0, 0.0, 0.0, 0.0, daily=[], status="insufficient_data")

    avg = total / n
    return ShadowSavings(
        total_savings_rs=round(total, 0),
        days_evaluated=n,
        avg_daily_rs=round(avg, 0),
        projected_monthly_rs=round(avg * 30, 0),
        projected_annual_rs=round(avg * 365, 0),
        daily=daily,
        status="ok",
    )
