"""Tests for the telemetry -> readings field mapping."""
from backend.services.telemetry_bridge import telemetry_to_reading


class TestTelemetryToReading:

    def test_watts_to_kw(self):
        r = telemetry_to_reading(total_load_w=312000, solar_w=40000, soc_pct=68)
        assert r["load_kw"] == 312.0
        assert r["solar_kw"] == 40.0
        assert r["battery_soc"] == 68.0

    def test_net_and_grid_import(self):
        # load 300kW, solar 100kW -> net import 200kW
        r = telemetry_to_reading(300000, 100000, 50)
        assert r["net_kw"] == 200.0
        assert r["grid_kw"] == 200.0

    def test_solar_surplus_floors_grid_at_zero(self):
        # solar exceeds load -> exporting; grid import must be 0, net negative
        r = telemetry_to_reading(50000, 120000, 90)
        assert r["net_kw"] == -70.0
        assert r["grid_kw"] == 0.0

    def test_handles_none(self):
        r = telemetry_to_reading(None, None, None)
        assert r["load_kw"] == 0.0
        assert r["solar_kw"] == 0.0
        assert r["battery_soc"] == 0.0
        assert r["grid_kw"] == 0.0
        assert r["net_kw"] == 0.0
