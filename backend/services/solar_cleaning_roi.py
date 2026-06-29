"""Soiling-loss → cleaning-ROI recommender.

The solar-health detector (``solar_health.run_solar_health``) measures a
Performance Ratio (PR). A clean, well-mounted array reaches PR ~0.95; when dust
films the glass the PR drops. PR already nets out irradiance (it is generation
divided by a clear-sky theoretical), so the gap below a clean array's PR is the
part attributable to *soiling* — exactly the loss a wash recovers.

This module turns that physical gap into a rupee decision:
  • how many kWh/day the dust is currently costing (vs a clean array),
  • how many rupees that is, and how many have already accrued since the last
    wash,
  • whether a wash pays for itself soon enough to do now, or whether to wait.

HONEST FRAMING — the software FINDS the loss and RECOMMENDS a wash; it does not
"deliver" the recovered energy. The operator (or cleaning contractor) acts; we
quantify and watch. Solar value is taken at the *self-consumption* rate (the
grid energy the panels offset), never an inflated peak rate — we don't overclaim.

Pure functions — no DB/framework — so they unit-test without a database.
"""
from dataclasses import dataclass

# PR of a clean, healthy array under the same clear-sky model solar_health uses.
# Matches the "recovers to ~0.95" assumption already baked into the soiling alert.
CLEAN_ARRAY_PR = 0.95

# Below this PR the array is dirty enough that a wash is worth costing out.
# (solar_health flags SOILING at PR < 0.85; we cost it from there.)
SOILING_PR_CEILING = 0.85

# How far ahead we look when deciding "clean now vs wait": if a wash pays back
# within this horizon it is worth doing now rather than bleeding loss until the
# next rain. ~Indian dry-season soiling typically wants a wash every 2-4 weeks.
DEFAULT_PAYBACK_HORIZON_DAYS = 14


def soiling_loss_fraction(pr_now: float, pr_clean: float = CLEAN_ARRAY_PR) -> float:
    """Fraction of *potential* generation currently lost to soiling.

    A clean array at pr_clean would produce 1.0; today's array at pr_now produces
    pr_now/pr_clean of that, so the lost fraction is (pr_clean - pr_now)/pr_clean.
    Returns 0 when the array is already at/above a clean PR.
    """
    pr_now = max(0.0, float(pr_now))
    pr_clean = max(0.01, float(pr_clean))
    if pr_now >= pr_clean:
        return 0.0
    return round((pr_clean - pr_now) / pr_clean, 4)


def daily_kwh_lost(measured_today_kwh: float, pr_now: float, pr_clean: float = CLEAN_ARRAY_PR) -> float:
    """kWh/day the soiling is costing, grounded in what the array ACTUALLY made today.

    If the array produced measured_today_kwh at pr_now, a clean array (pr_clean)
    on the same day would have produced measured_today_kwh * (pr_clean/pr_now);
    the difference is the soiling loss. Anchoring on measured output (not a
    nameplate estimate) keeps the number defensible.
    """
    measured = max(0.0, float(measured_today_kwh))
    pr_now = max(0.0, float(pr_now))
    pr_clean = max(0.01, float(pr_clean))
    if measured <= 0 or pr_now <= 0 or pr_now >= pr_clean:
        return 0.0
    clean_output = measured * (pr_clean / pr_now)
    return round(clean_output - measured, 1)


@dataclass
class CleaningAdvice:
    pr_now: float
    pr_clean: float
    loss_fraction: float            # share of potential generation lost to dust
    daily_kwh_lost: float           # kWh/day bleeding to soiling right now
    daily_rs_lost: float            # ₹/day at the self-consumption rate
    cumulative_rs_lost: float       # ₹ lost since the last wash (days_since_clean)
    cleaning_cost_rs: float         # what a wash costs (labour + water)
    payback_days: float | None      # days for the daily loss to repay a wash
    recommendation: str             # "clean_now" | "monitor" | "clean_not_needed"
    rationale: str                  # human-readable, honest


def cleaning_advice(
    measured_today_kwh: float,
    pr_now: float,
    solar_value_per_kwh: float,
    cleaning_cost_rs: float,
    *,
    days_since_clean: int = 0,
    pr_clean: float = CLEAN_ARRAY_PR,
    payback_horizon_days: int = DEFAULT_PAYBACK_HORIZON_DAYS,
) -> CleaningAdvice:
    """Decide whether to wash the panels now, and justify it in rupees.

    measured_today_kwh : solar kWh generated today (from get_solar_generation).
    pr_now             : measured Performance Ratio (from run_solar_health).
    solar_value_per_kwh: ₹ each self-consumed solar kWh is worth = the grid rate
                         it offsets (use the normal/blended rate, NOT peak).
    cleaning_cost_rs   : labour + water for one wash of this array.
    days_since_clean   : days since the last wash, to accrue the loss already taken.

    Recommendation:
      • "clean_not_needed" — PR healthy / no measurable soiling loss.
      • "clean_now"        — a wash repays within payback_horizon_days, OR the loss
                             already accrued since the last wash exceeds a wash's cost.
      • "monitor"          — soiling present but a wash does not yet pay back; watch.
    """
    pr_now = max(0.0, float(pr_now))
    cleaning_cost_rs = max(0.0, float(cleaning_cost_rs))
    days_since_clean = max(0, int(days_since_clean))

    frac = soiling_loss_fraction(pr_now, pr_clean)
    kwh_lost = daily_kwh_lost(measured_today_kwh, pr_now, pr_clean)
    daily_rs = round(kwh_lost * max(0.0, float(solar_value_per_kwh)), 2)
    cumulative_rs = round(daily_rs * days_since_clean, 2)

    if daily_rs <= 0:
        return CleaningAdvice(
            pr_now=round(pr_now, 3), pr_clean=pr_clean, loss_fraction=frac,
            daily_kwh_lost=kwh_lost, daily_rs_lost=daily_rs,
            cumulative_rs_lost=cumulative_rs, cleaning_cost_rs=cleaning_cost_rs,
            payback_days=None, recommendation="clean_not_needed",
            rationale=(
                f"Performance Ratio {pr_now:.2f} is at a clean array's level "
                f"(~{pr_clean:.2f}). No measurable soiling loss — a wash would not pay back."
            ),
        )

    payback_days = round(cleaning_cost_rs / daily_rs, 1) if daily_rs > 0 else None

    if cumulative_rs >= cleaning_cost_rs > 0:
        rec = "clean_now"
        rationale = (
            f"PR {pr_now:.2f} (clean ~{pr_clean:.2f}) → losing ~{kwh_lost:.0f} kWh/day "
            f"(₹{daily_rs:.0f}/day). Since the last wash {days_since_clean}d ago you have "
            f"already lost ₹{cumulative_rs:.0f}, more than the ₹{cleaning_cost_rs:.0f} a wash "
            f"costs. Clean now — every extra day is pure loss."
        )
    elif payback_days is not None and payback_days <= payback_horizon_days:
        rec = "clean_now"
        rationale = (
            f"PR {pr_now:.2f} (clean ~{pr_clean:.2f}) → losing ~{kwh_lost:.0f} kWh/day "
            f"(₹{daily_rs:.0f}/day). A ₹{cleaning_cost_rs:.0f} wash repays itself in "
            f"~{payback_days:.0f} days, well within the {payback_horizon_days}-day window. "
            f"Worth cleaning now."
        )
    else:
        rec = "monitor"
        rationale = (
            f"PR {pr_now:.2f} (clean ~{pr_clean:.2f}) → losing ~{kwh_lost:.0f} kWh/day "
            f"(₹{daily_rs:.0f}/day), but a ₹{cleaning_cost_rs:.0f} wash takes "
            f"~{payback_days:.0f} days to repay (> {payback_horizon_days}-day window). "
            f"Monitor — wash once the loss accrues or before a long dry spell."
        )

    return CleaningAdvice(
        pr_now=round(pr_now, 3), pr_clean=pr_clean, loss_fraction=frac,
        daily_kwh_lost=kwh_lost, daily_rs_lost=daily_rs,
        cumulative_rs_lost=cumulative_rs, cleaning_cost_rs=cleaning_cost_rs,
        payback_days=payback_days, recommendation=rec, rationale=rationale,
    )
