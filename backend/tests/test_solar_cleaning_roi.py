"""Tests for the soiling-loss → cleaning-ROI recommender."""
import math

from backend.services.solar_cleaning_roi import (
    CLEAN_ARRAY_PR,
    cleaning_advice,
    daily_kwh_lost,
    soiling_loss_fraction,
)


class TestSoilingLossFraction:
    def test_clean_array_no_loss(self):
        assert soiling_loss_fraction(0.95) == 0.0
        assert soiling_loss_fraction(0.98) == 0.0  # above clean → clamp to 0

    def test_dirty_array_loss(self):
        # PR 0.75 vs clean 0.95: lost fraction = (0.95-0.75)/0.95 ≈ 0.2105
        assert math.isclose(soiling_loss_fraction(0.75), 0.2105, abs_tol=1e-3)

    def test_worse_pr_more_loss(self):
        assert soiling_loss_fraction(0.60) > soiling_loss_fraction(0.80)


class TestDailyKwhLost:
    def test_measured_anchored_loss(self):
        # Array made 760 kWh today at PR 0.76; clean (0.95) would make 760*0.95/0.76 = 950
        # → 190 kWh lost.
        assert math.isclose(daily_kwh_lost(760, 0.76), 190.0, abs_tol=0.5)

    def test_no_loss_when_clean(self):
        assert daily_kwh_lost(900, 0.95) == 0.0
        assert daily_kwh_lost(900, 0.97) == 0.0

    def test_zero_generation_zero_loss(self):
        assert daily_kwh_lost(0, 0.50) == 0.0


class TestCleaningAdvice:
    def test_healthy_array_not_needed(self):
        a = cleaning_advice(900, pr_now=0.95, solar_value_per_kwh=6.10, cleaning_cost_rs=2000)
        assert a.recommendation == "clean_not_needed"
        assert a.daily_rs_lost == 0.0
        assert a.payback_days is None

    def test_heavy_soiling_fast_payback_clean_now(self):
        # 760 kWh at PR 0.76 → 190 kWh/day lost; at ₹6.10 that's ₹1159/day.
        # A ₹2000 wash repays in ~1.7 days → clean_now.
        a = cleaning_advice(760, pr_now=0.76, solar_value_per_kwh=6.10, cleaning_cost_rs=2000)
        assert a.recommendation == "clean_now"
        assert a.daily_kwh_lost == 190.0
        assert math.isclose(a.daily_rs_lost, 1159.0, abs_tol=1.0)
        assert a.payback_days is not None and a.payback_days < 14

    def test_mild_soiling_slow_payback_monitors(self):
        # Tiny array, mild soiling, expensive wash → payback beyond horizon → monitor.
        # 20 kWh at PR 0.84 → lost = 20*(0.95/0.84-1) ≈ 2.6 kWh/day; at ₹4 ≈ ₹10.5/day.
        # ₹2000 wash repays in ~190 days → monitor.
        a = cleaning_advice(20, pr_now=0.84, solar_value_per_kwh=4.0, cleaning_cost_rs=2000)
        assert a.recommendation == "monitor"
        assert a.daily_rs_lost > 0
        assert a.payback_days > 14

    def test_accrued_loss_exceeds_cost_forces_clean_now(self):
        # Mild daily loss but a long time since the last wash → cumulative loss has
        # already exceeded a wash's cost → clean_now even though daily payback is slow.
        a = cleaning_advice(
            20, pr_now=0.84, solar_value_per_kwh=4.0, cleaning_cost_rs=2000,
            days_since_clean=300,
        )
        assert a.recommendation == "clean_now"
        assert a.cumulative_rs_lost >= a.cleaning_cost_rs

    def test_self_consumption_rate_not_peak(self):
        # Sanity: rupee loss scales with the rate the caller passes (we never inflate it).
        cheap = cleaning_advice(760, 0.76, solar_value_per_kwh=4.20, cleaning_cost_rs=2000)
        normal = cleaning_advice(760, 0.76, solar_value_per_kwh=6.10, cleaning_cost_rs=2000)
        assert normal.daily_rs_lost > cheap.daily_rs_lost

    def test_rationale_is_populated(self):
        a = cleaning_advice(760, 0.76, solar_value_per_kwh=6.10, cleaning_cost_rs=2000)
        assert "PR" in a.rationale and "₹" in a.rationale
        assert a.pr_clean == CLEAN_ARRAY_PR
