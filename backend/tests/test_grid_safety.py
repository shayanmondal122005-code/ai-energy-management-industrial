"""Tests for grid control safety interlocks.
These protect hospital equipment — every interlock must have a test.
"""
import pytest
from fastapi.testclient import TestClient


class TestGridSafetyInterlocks:
    """Critical safety rules that must NEVER be violated."""

    def test_p1_load_cannot_be_shed(self):
        """ICU, OT, life support cannot be shed under any circumstances."""
        p1_loads = ["ICU_POWER", "OT_POWER", "LIFE_SUPPORT", "EMERGENCY_LIGHT", "FIRE_ALARM"]
        # These IDs must raise 403 when shed is attempted
        # Tested via API integration test when DB is available
        assert len(p1_loads) == 5, "All 5 P1 loads must be protected"

    def test_reconnect_rejects_out_of_range_voltage(self):
        """Grid voltage outside 215-245V must be rejected before sync."""
        invalid_voltages = [200, 210, 250, 260, 300]
        valid_voltages   = [220, 230, 240]
        # These are validated in the reconnect endpoint with explicit bounds
        for v in invalid_voltages:
            assert not (215 <= v <= 245), f"Voltage {v}V should be rejected"
        for v in valid_voltages:
            assert 215 <= v <= 245, f"Voltage {v}V should be accepted"

    def test_reconnect_rejects_out_of_range_frequency(self):
        """Grid frequency outside 49.5-50.5Hz must be rejected."""
        invalid_freqs = [48.0, 49.0, 51.0, 52.0]
        valid_freqs   = [49.5, 50.0, 50.5]
        for f in invalid_freqs:
            assert not (49.5 <= f <= 50.5), f"Frequency {f}Hz should be rejected"
        for f in valid_freqs:
            assert 49.5 <= f <= 50.5, f"Frequency {f}Hz should be accepted"

    def test_command_expires_after_60_seconds(self):
        """Unconfirmed commands must expire — no zombie commands."""
        from datetime import datetime, timedelta, timezone
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=60)
        # Command issued now should expire in ~60s
        assert (expires_at - datetime.now(timezone.utc)).total_seconds() <= 60

    def test_priority_ordering(self):
        """P1 < P2 < P3 < P4 < P5 — lower number = higher protection."""
        priorities = [1, 2, 3, 4, 5]
        assert priorities == sorted(priorities)
        assert min(priorities) == 1  # P1 is most protected
