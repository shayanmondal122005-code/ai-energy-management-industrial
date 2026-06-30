"""Tier-1.5 — electrical safety detectors."""
from backend.services.solar_om.detectors.safety import (
    detect_arc_fault,
    detect_ground_fault,
    detect_open_or_degraded_string,
    detect_riso_trend,
)
from backend.services.solar_om.models import Severity


class TestGroundFault:
    def test_flag_set_is_critical(self):
        d = detect_ground_fault("P1", "INV1", ground_fault_flag=True,
                                riso_kohm=900, riso_threshold_kohm=600)
        assert d.severity == Severity.CRITICAL and d.risk_note

    def test_riso_below_threshold_is_critical(self):
        d = detect_ground_fault("P1", "INV1", ground_fault_flag=False,
                                riso_kohm=400, riso_threshold_kohm=600)
        assert d is not None and d.type == "ground_fault"

    def test_healthy_no_alert(self):
        assert detect_ground_fault("P1", "INV1", ground_fault_flag=False,
                                   riso_kohm=900, riso_threshold_kohm=600) is None


class TestRisoTrend:
    def test_declining_riso_flags_investigate(self):
        d = detect_riso_trend("P1", "INV1", [900, 820, 760, 700])
        assert d is not None and d.severity == Severity.INVESTIGATE
        assert d.evidence["drop_pct"] > 10

    def test_stable_riso_no_alert(self):
        assert detect_riso_trend("P1", "INV1", [850, 860, 840, 855]) is None

    def test_rising_riso_no_alert(self):
        assert detect_riso_trend("P1", "INV1", [700, 760, 820, 900]) is None


class TestArcFault:
    def test_arc_flag_critical(self):
        d = detect_arc_fault("P1", "INV1", arc_fault_flag=True)
        assert d.severity == Severity.CRITICAL and "FIRE RISK" in d.risk_note

    def test_no_arc_no_alert(self):
        assert detect_arc_fault("P1", "INV1", arc_fault_flag=False) is None


class TestOpenVsDegraded:
    def test_open_circuit_voltage_present(self):
        d = detect_open_or_degraded_string(
            "P1", "INV1", "S1", dc_current=0.0, dc_voltage=620.0,
            peer_deficit_frac=1.0, persistent=True,
            rated_share=0.25, expected_kwh_window=200, tariff_rate=6.0)
        assert d.type == "string_open" and d.severity == Severity.CRITICAL
        assert d.rupee_impact_per_day > 0

    def test_degraded_resistive_string(self):
        d = detect_open_or_degraded_string(
            "P1", "INV1", "S1", dc_current=8.0, dc_voltage=610.0,
            peer_deficit_frac=0.15, persistent=True,
            rated_share=0.25, expected_kwh_window=200, tariff_rate=6.0)
        assert d.type == "string_degraded" and d.severity == Severity.INVESTIGATE

    def test_degraded_suppressed_when_recovers_on_cleaning(self):
        # If it recovers after cleaning it was soiling, not a resistive fault.
        d = detect_open_or_degraded_string(
            "P1", "INV1", "S1", dc_current=8.0, dc_voltage=610.0,
            peer_deficit_frac=0.15, persistent=True, recovered_on_cleaning=True)
        assert d is None

    def test_degraded_suppressed_when_clock_locked(self):
        d = detect_open_or_degraded_string(
            "P1", "INV1", "S1", dc_current=8.0, dc_voltage=610.0,
            peer_deficit_frac=0.15, persistent=True, clock_locked=True)
        assert d is None

    def test_healthy_string_no_alert(self):
        d = detect_open_or_degraded_string(
            "P1", "INV1", "S1", dc_current=9.8, dc_voltage=620.0,
            peer_deficit_frac=0.01, persistent=True)
        assert d is None

    def test_open_not_flagged_at_low_light(self):
        # ~0 current with voltage present BUT peers are also dark (low peer deficit) →
        # this is dawn/dusk/cloud, NOT a broken string. Must not raise a false critical.
        d = detect_open_or_degraded_string(
            "P1", "INV1", "S1", dc_current=0.0, dc_voltage=120.0,
            peer_deficit_frac=0.02, persistent=True)
        assert d is None
