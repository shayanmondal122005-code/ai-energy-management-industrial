"""Detector 2 — inverter downtime / health."""
from datetime import datetime, timedelta, timezone

from backend.services.solar_om.detectors.inverter_health import (
    InvIntervalSample,
    detect_inverter_derate,
    detect_inverter_outage,
    detect_predictive_faultcode,
)
from backend.services.solar_om.models import Severity

IST = timezone(timedelta(hours=5, minutes=30))


def _samples(n, *, poa=700.0, ac, expected=40000.0, start_h=10):
    base = datetime(2026, 6, 29, start_h, 0, tzinfo=IST)
    return [InvIntervalSample(ts=base + timedelta(minutes=15 * i), poa_wm2=poa,
                              ac_power_w=ac, expected_w=expected) for i in range(n)]


class TestOutage:
    def test_sustained_outage_is_critical_with_rupees(self):
        # 4×15min = 60 min of zero export under POA 700 → critical, ₹ accumulating.
        s = _samples(4, ac=0.0)
        d = detect_inverter_outage("P1", "INV1", s, tariff_rate=6.0, interval_hours=0.25)
        assert d is not None and d.severity == Severity.CRITICAL
        assert d.evidence["outage_minutes"] == 60.0
        # 4 intervals × 40kW × 0.25h = 40 kWh × ₹6 = ₹240 lost so far.
        assert abs(d.rupee_accumulated - 240.0) < 1.0
        assert d.rupee_impact_per_day > 0

    def test_short_blip_not_flagged(self):
        # Only 2×15 = 30 min... wait, must be >15 min; 1 interval = 15 min is the edge.
        s = _samples(1, ac=0.0)
        d = detect_inverter_outage("P1", "INV1", s, tariff_rate=6.0, interval_hours=0.25)
        assert d is None  # 15 min is not > 15 min

    def test_night_not_outage(self):
        s = _samples(4, ac=0.0, poa=0.0)  # no sun → not an outage
        assert detect_inverter_outage("P1", "INV1", s, tariff_rate=6.0, interval_hours=0.25) is None

    def test_normal_production_no_outage(self):
        s = _samples(4, ac=39000.0)  # producing normally
        assert detect_inverter_outage("P1", "INV1", s, tariff_rate=6.0, interval_hours=0.25) is None

    def test_outage_detected_despite_dusk_last_interval(self):
        # All-day outage but the final reading is at dusk (POA below floor → no info).
        # The dusk interval must be skipped, not allowed to mask the ongoing outage.
        day = _samples(4, ac=0.0, poa=700.0)               # 4 high-sun intervals, out
        dusk = _samples(1, ac=0.0, poa=50.0, start_h=18)   # final low-sun interval
        d = detect_inverter_outage("P1", "INV1", day + dusk, tariff_rate=6.0, interval_hours=0.25)
        assert d is not None and d.severity == Severity.CRITICAL
        assert d.evidence["outage_minutes"] == 60.0


class TestDerate:
    def test_persistent_shortfall_flagged(self):
        s = _samples(6, ac=30000.0, expected=40000.0)  # 25% short, sustained
        d = detect_inverter_derate("P1", "INV1", s, clipping_kw=None)
        assert d is not None and d.severity == Severity.INVESTIGATE
        assert d.evidence["mean_shortfall_pct"] > 15

    def test_clipping_window_excluded(self):
        # Expected above the clipping cap → legitimate clipping, not a derate fault.
        s = _samples(6, ac=30000.0, expected=40000.0)
        d = detect_inverter_derate("P1", "INV1", s, clipping_kw=20.0)  # 20kW cap < expected
        assert d is None


class TestPredictive:
    def test_rising_faultcode_schedules(self):
        d = detect_predictive_faultcode("P1", "INV1", code=302, weekly_counts=[1, 3, 5, 9])
        assert d is not None and d.severity == Severity.INFO

    def test_stable_faultcode_no_alert(self):
        assert detect_predictive_faultcode("P1", "INV1", 302, [4, 4, 3, 4]) is None
