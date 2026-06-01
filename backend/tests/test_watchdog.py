"""Tests for safety watchdog — every interlock must pass."""
import pytest
from datetime import datetime, timedelta, timezone
from backend.services.watchdog import run_watchdog, MalfunctionType, THRESHOLDS


def _reading(soc=70.0, load=300.0, solar=150.0, temp=28.0, minutes_ago=5):
    ts = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return type("R", (), {
        "timestamp"  : ts,
        "battery_soc": soc,
        "load_kw"    : load,
        "solar_kw"   : solar,
        "battery_temp": temp,
    })()


class TestWatchdogSafe:
    def test_all_clear_when_normal(self):
        readings = [_reading(soc=70, load=300, solar=150, temp=28, minutes_ago=i*15) for i in range(5, 0, -1)]
        r = run_watchdog(readings, "Test Hospital", "fac-1", solar_kw_installed=200)
        assert r.safe is True
        assert r.malfunctions == []

    def test_no_readings_triggers_stale(self):
        r = run_watchdog([], "Test Hospital", "fac-1", solar_kw_installed=200)
        assert r.safe is False
        types = [m.type for m in r.malfunctions]
        assert MalfunctionType.STALE_DATA in types

    def test_old_reading_triggers_stale(self):
        readings = [_reading(minutes_ago=25)]  # 25 min old > 20 min threshold
        r = run_watchdog(readings, "Test Hospital", "fac-1", solar_kw_installed=200)
        assert r.safe is False
        types = [m.type for m in r.malfunctions]
        assert MalfunctionType.STALE_DATA in types

    def test_fresh_reading_no_stale(self):
        readings = [_reading(minutes_ago=5)]
        r = run_watchdog(readings, "Test Hospital", "fac-1", solar_kw_installed=200)
        stale = [m for m in r.malfunctions if m.type == MalfunctionType.STALE_DATA]
        assert stale == []


class TestWatchdogSoCCritical:
    def test_critical_soc_detected(self):
        readings = [_reading(soc=10.0, minutes_ago=5)]
        r = run_watchdog(readings, "Test Hospital", "fac-1", solar_kw_installed=200)
        assert r.safe is False
        types = [m.type for m in r.malfunctions]
        assert MalfunctionType.SOC_CRITICAL in types

    def test_safe_soc_no_alert(self):
        readings = [_reading(soc=68.0, minutes_ago=5)]
        r = run_watchdog(readings, "Test Hospital", "fac-1", solar_kw_installed=200)
        soc_alerts = [m for m in r.malfunctions if m.type == MalfunctionType.SOC_CRITICAL]
        assert soc_alerts == []


class TestWatchdogSoCFreefall:
    def test_freefall_detected(self):
        # SoC drops 2%/min — above 1.5%/min threshold
        readings = [
            _reading(soc=80, minutes_ago=6),
            _reading(soc=78, minutes_ago=5),
            _reading(soc=76, minutes_ago=4),
            _reading(soc=70, minutes_ago=3),  # 6% in 1 min = freefall
        ]
        r = run_watchdog(readings, "Test Hospital", "fac-1", solar_kw_installed=200)
        types = [m.type for m in r.malfunctions]
        assert MalfunctionType.SOC_FREEFALL in types

    def test_normal_discharge_no_freefall(self):
        # Normal: ~0.3%/min discharge
        readings = [
            _reading(soc=70.0, minutes_ago=8),
            _reading(soc=69.7, minutes_ago=6),
            _reading(soc=69.4, minutes_ago=4),
            _reading(soc=69.1, minutes_ago=2),
        ]
        r = run_watchdog(readings, "Test Hospital", "fac-1", solar_kw_installed=200)
        ff = [m for m in r.malfunctions if m.type == MalfunctionType.SOC_FREEFALL]
        assert ff == []


class TestWatchdogTemperature:
    def test_high_temp_detected(self):
        readings = [_reading(temp=47.0, minutes_ago=2)]
        r = run_watchdog(readings, "Test Hospital", "fac-1", solar_kw_installed=200)
        assert r.safe is False
        types = [m.type for m in r.malfunctions]
        assert MalfunctionType.BATTERY_TEMP_HIGH in types

    def test_normal_temp_safe(self):
        readings = [_reading(temp=32.0, minutes_ago=2)]
        r = run_watchdog(readings, "Test Hospital", "fac-1", solar_kw_installed=200)
        temp_alerts = [m for m in r.malfunctions if m.type == MalfunctionType.BATTERY_TEMP_HIGH]
        assert temp_alerts == []


class TestWatchdogSolarFault:
    def test_solar_drop_detected_daytime(self):
        # Build reading with a specific hour during daytime
        from datetime import datetime, timezone, timedelta
        base = datetime.now(timezone.utc).replace(hour=12, minute=0)
        r1 = type("R", (), {"timestamp": base - timedelta(minutes=15),
                             "battery_soc": 70, "load_kw": 300,
                             "solar_kw": 180, "battery_temp": 28})()
        r2 = type("R", (), {"timestamp": base,
                             "battery_soc": 70, "load_kw": 300,
                             "solar_kw": 100, "battery_temp": 28})()  # 80kW drop
        result = run_watchdog([r1, r2], "Test Hospital", "fac-1", solar_kw_installed=200)
        types = [m.type for m in result.malfunctions]
        assert MalfunctionType.SOLAR_FAULT in types

    def test_no_false_solar_fault_at_night(self):
        # Night drop is expected
        from datetime import datetime, timezone, timedelta
        base = datetime.now(timezone.utc).replace(hour=22, minute=0)
        r1 = type("R", (), {"timestamp": base - timedelta(minutes=15),
                             "battery_soc": 70, "load_kw": 300,
                             "solar_kw": 100, "battery_temp": 28})()
        r2 = type("R", (), {"timestamp": base,
                             "battery_soc": 70, "load_kw": 300,
                             "solar_kw": 0, "battery_temp": 28})()
        result = run_watchdog([r1, r2], "Test Hospital", "fac-1", solar_kw_installed=200)
        solar_faults = [m for m in result.malfunctions if m.type == MalfunctionType.SOLAR_FAULT]
        assert solar_faults == []


class TestWatchdogSensorAnomaly:
    def test_impossible_load_detected(self):
        readings = [_reading(load=5000, minutes_ago=2)]  # 5000 kW impossible
        r = run_watchdog(readings, "Test Hospital", "fac-1", solar_kw_installed=200)
        types = [m.type for m in r.malfunctions]
        assert MalfunctionType.SENSOR_ANOMALY in types

    def test_normal_load_no_anomaly(self):
        readings = [_reading(load=350, minutes_ago=2)]
        r = run_watchdog(readings, "Test Hospital", "fac-1", solar_kw_installed=200)
        anomalies = [m for m in r.malfunctions if m.type == MalfunctionType.SENSOR_ANOMALY]
        assert anomalies == []
