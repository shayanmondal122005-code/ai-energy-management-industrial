"""Detector 1 — soiling."""
from backend.services.solar_om.detectors.base import InMemoryAlertStore
from backend.services.solar_om.detectors.soiling import detect_soiling, soiling_rate_pct_per_day
from backend.services.solar_om.models import AlertStatus


def _declining_series(start=0.85, per_day=0.005, days=10):
    return [start - per_day * d for d in range(days)]


class TestSoilingRate:
    def test_flat_series_zero_rate(self):
        assert soiling_rate_pct_per_day([0.83] * 10) == 0.0

    def test_declining_series_positive_rate(self):
        # 0.5% of PR per day decline ≈ 0.6%/day of mean.
        sr = soiling_rate_pct_per_day(_declining_series())
        assert 0.4 < sr < 0.8


class TestDetectSoiling:
    def test_fires_when_loss_exceeds_threshold(self):
        d = detect_soiling(
            "PLANT-001", _declining_series(days=12),
            days_since_clean=12, expected_kwh_day=480.0, tariff_rate=6.0,
            cleaning_cost=3000.0, theta_soil_pct=5.0,
        )
        assert d is not None and d.type == "soiling"
        assert d.rupee_impact_per_day > 0
        assert d.evidence["loss_pct"] > 5.0

    def test_recommends_cleaning_when_accumulated_exceeds_cost(self):
        # Cheap cleaning cost → accumulated loss should justify cleaning now.
        d = detect_soiling(
            "PLANT-001", _declining_series(days=14),
            days_since_clean=14, expected_kwh_day=480.0, tariff_rate=6.0,
            cleaning_cost=500.0,
        )
        assert d.evidence["recommend_clean"] is True
        assert "Clean panels now" in d.recommended_action

    def test_no_alert_when_uniform_false(self):
        # Non-uniform decline is a string fault, not soiling.
        d = detect_soiling(
            "PLANT-001", _declining_series(days=12), days_since_clean=12,
            expected_kwh_day=480, tariff_rate=6.0, cleaning_cost=500,
            uniform_across_strings=False,
        )
        assert d is None

    def test_no_alert_on_clean_flat_pr(self):
        d = detect_soiling(
            "PLANT-001", [0.83] * 12, days_since_clean=12,
            expected_kwh_day=480, tariff_rate=6.0, cleaning_cost=500,
        )
        assert d is None


class TestStoreReconcile:
    def test_reidempotent_open_then_update(self):
        store = InMemoryAlertStore()
        from datetime import datetime, timezone
        ts = datetime(2026, 6, 29, tzinfo=timezone.utc)
        d = detect_soiling("PLANT-001", _declining_series(days=12), days_since_clean=12,
                           expected_kwh_day=480, tariff_rate=6.0, cleaning_cost=3000)
        store.reconcile([d], ts, scope_types={"soiling"})
        store.reconcile([d], ts, scope_types={"soiling"})   # second run must not duplicate
        assert len(store.open_by_type("soiling")) == 1
        # Condition clears (no draft) → alert closes.
        store.reconcile([], ts, scope_types={"soiling"})
        assert len(store.open_by_type("soiling")) == 0
        assert store.closed()[0]["status"] == AlertStatus.RESOLVED
