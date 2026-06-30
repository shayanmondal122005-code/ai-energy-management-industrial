"""Detector 3 — string / MPPT underperformance."""
from backend.services.solar_om.detectors.string_mppt import (
    detect_string_underperformance,
    is_clock_locked,
    string_current_ratio,
)
from backend.services.solar_om.models import Severity


class TestRatio:
    def test_ratio_vs_peers(self):
        assert string_current_ratio(8.0, [10.0, 10.0, 10.2]) < 0.85

    def test_no_peers_returns_one(self):
        assert string_current_ratio(8.0, []) == 1.0


class TestUnderperformance:
    def test_healthy_string_no_alert(self):
        d = detect_string_underperformance(
            "P1", "INV1", "S1", [1.0, 0.99, 1.01, 1.0],
            expected_kwh_window=200, rated_share=0.25, tariff_rate=6.0)
        assert d is None

    def test_mild_deficit_investigate(self):
        # ~10% below peers, sustained → investigate.
        d = detect_string_underperformance(
            "P1", "INV1", "S1", [0.90, 0.89, 0.91, 0.90],
            expected_kwh_window=200, rated_share=0.25, tariff_rate=6.0)
        assert d is not None and d.severity == Severity.INVESTIGATE
        assert 8 <= d.evidence["mean_deficit_pct"] <= 15
        assert d.rupee_impact_per_day > 0

    def test_large_deficit_flags_open_substring(self):
        d = detect_string_underperformance(
            "P1", "INV1", "S1", [0.7, 0.72, 0.68, 0.70],
            expected_kwh_window=200, rated_share=0.25, tariff_rate=6.0)
        assert "open substring" in d.recommended_action

    def test_clock_locked_is_shading_info(self):
        d = detect_string_underperformance(
            "P1", "INV1", "S1", [0.6, 0.62, 0.61],
            expected_kwh_window=200, rated_share=0.25, tariff_rate=6.0,
            clock_locked=True)
        assert d.severity == Severity.INFO
        assert "SHADING" in d.recommended_action

    def test_gate_downweight_reduces_confidence(self):
        full = detect_string_underperformance(
            "P1", "INV1", "S1", [0.85, 0.86, 0.84],
            expected_kwh_window=200, rated_share=0.25, tariff_rate=6.0)
        dw = detect_string_underperformance(
            "P1", "INV1", "S1", [0.85, 0.86, 0.84],
            expected_kwh_window=200, rated_share=0.25, tariff_rate=6.0,
            confidence_factor=0.5)
        assert dw.confidence < full.confidence


class TestClockLocked:
    def test_same_hour_across_days_is_shading(self):
        assert is_clock_locked([{8, 9}, {8, 9}, {8}]) is True

    def test_different_hours_not_shading(self):
        assert is_clock_locked([{8}, {13}, {16}]) is False
