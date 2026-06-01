"""Tests for solar health detectors."""
import pytest
from datetime import datetime, timedelta
from backend.services.solar_health import run_solar_health


def _make_reading(hour: int, solar_kw: float, days_ago: int = 0) -> dict:
    ts = datetime.now().replace(hour=hour, minute=0, second=0) - timedelta(days=days_ago)
    return {"timestamp": ts, "solar_kw": solar_kw}


class TestSolarHealth:
    def test_insufficient_data_returns_no_alerts(self):
        result = run_solar_health([_make_reading(12, 100)] * 3)
        assert result["status"] == "insufficient_data"
        assert result["alerts"] == []

    def test_good_performance_no_alerts(self):
        readings = [_make_reading(12, 140)] * 20  # PR = 140/(200*0.65) = 1.07 → good
        result = run_solar_health(readings, solar_cap=200)
        soiling_alerts = [a for a in result["alerts"] if a["type"] == "SOILING"]
        assert soiling_alerts == []

    def test_low_pr_triggers_soiling_warning(self):
        # PR = 70/(200*0.65) = 0.538 → below 0.75 threshold
        readings = [_make_reading(12, 70)] * 20
        result = run_solar_health(readings, solar_cap=200)
        soiling = [a for a in result["alerts"] if a["type"] == "SOILING"]
        assert len(soiling) == 1
        assert soiling[0]["severity"] == "WARNING"

    def test_sudden_drop_triggers_critical(self):
        readings = [
            _make_reading(12, 180),
            _make_reading(12, 170),
            _make_reading(12, 160),
            _make_reading(12, 100),  # 80kW drop → CRITICAL
        ]
        result = run_solar_health(readings, solar_cap=200)
        drop_alerts = [a for a in result["alerts"] if a["type"] == "SUDDEN_DROP"]
        assert len(drop_alerts) == 1
        assert drop_alerts[0]["severity"] == "CRITICAL"

    def test_no_drop_at_night(self):
        readings = [
            _make_reading(22, 180),
            _make_reading(22, 10),
            _make_reading(22, 5),
            _make_reading(22, 0),
        ]
        result = run_solar_health(readings, solar_cap=200)
        drop_alerts = [a for a in result["alerts"] if a["type"] == "SUDDEN_DROP"]
        assert drop_alerts == []  # no alert at night hour
