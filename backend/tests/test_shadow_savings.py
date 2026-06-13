"""Tests for shadow-savings — realized savings replayed from real history."""
from datetime import datetime, timedelta, timezone

from backend.services.shadow_savings import compute_shadow_savings


def _day_rows(day: datetime, load_kw: float, solar_kw: float, soc: float = 50.0, hours: int = 24):
    """Generate `hours` hourly rows for one calendar day."""
    return [(day + timedelta(hours=h), load_kw, solar_kw, soc) for h in range(hours)]


class TestShadowSavings:

    def test_insufficient_data_returns_zero(self):
        """A partial day (< MIN_HOURS_PER_DAY) is not counted."""
        day = datetime(2026, 6, 1, tzinfo=timezone.utc)
        rows = _day_rows(day, load_kw=200, solar_kw=0, hours=10)  # only 10 hours
        s = compute_shadow_savings(rows, state_tariff="West Bengal - CESC", battery_kwh=500)
        assert s.status == "insufficient_data"
        assert s.total_savings_rs == 0
        assert s.days_evaluated == 0

    def test_full_day_is_evaluated(self):
        day = datetime(2026, 6, 1, tzinfo=timezone.utc)
        rows = _day_rows(day, load_kw=250, solar_kw=0)
        s = compute_shadow_savings(rows, state_tariff="West Bengal - CESC", battery_kwh=500)
        assert s.status == "ok"
        assert s.days_evaluated == 1
        assert len(s.daily) == 1
        assert s.daily[0]["date"] == "2026-06-01"

    def test_savings_never_negative(self):
        day = datetime(2026, 6, 1, tzinfo=timezone.utc)
        rows = _day_rows(day, load_kw=200, solar_kw=0)
        s = compute_shadow_savings(rows, state_tariff="West Bengal - CESC", battery_kwh=500)
        assert s.total_savings_rs >= 0
        for d in s.daily:
            assert d["savings_rs"] >= 0

    def test_multiple_days_accumulate_and_project(self):
        rows = []
        for i in range(3):
            day = datetime(2026, 6, 1, tzinfo=timezone.utc) + timedelta(days=i)
            # Evening-peak profile so peak-shaving + arbitrage produce real savings
            for h in range(24):
                load = 350.0 if 18 <= h <= 21 else 200.0
                rows.append((day + timedelta(hours=h), load, 0.0, 60.0))
        s = compute_shadow_savings(rows, state_tariff="West Bengal - CESC", battery_kwh=500)
        assert s.days_evaluated == 3
        assert s.total_savings_rs > 0, "Evening-peak hospital profile should yield savings"
        # Projections are simple linear extrapolations of the average day
        assert s.projected_monthly_rs == round(s.avg_daily_rs * 30, 0)
        assert s.projected_annual_rs == round(s.avg_daily_rs * 365, 0)

    def test_sparse_hours_are_filled(self):
        """A day missing a couple of hours (but >= 20) is still evaluated, not skipped."""
        day = datetime(2026, 6, 1, tzinfo=timezone.utc)
        rows = [(day + timedelta(hours=h), 250.0, 0.0, 55.0) for h in range(24) if h not in (3, 4)]
        s = compute_shadow_savings(rows, state_tariff="West Bengal - CESC", battery_kwh=500)
        assert s.days_evaluated == 1
