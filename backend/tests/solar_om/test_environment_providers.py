"""Open-Meteo satellite provider parser (network-free)."""
from datetime import datetime, timezone

from backend.services.solar_om.environment import OpenMeteoSatelliteProvider, parse_open_meteo

_SAMPLE = {"hourly": {
    "time": ["2026-06-30T03:00", "2026-06-30T05:00", "2026-06-30T22:00"],
    "shortwave_radiation": [420.0, 780.0, 0.0],
    "temperature_2m": [31.0, 35.0, 28.0],
}}


def test_parse_maps_utc_hours():
    out = parse_open_meteo(_SAMPLE)
    assert out["2026063005"] == (780.0, 35.0)
    assert out["2026063022"] == (0.0, 28.0)


def test_missing_ghi_defaults_zero():
    data = {"hourly": {"time": ["2026-06-30T05:00"],
                       "shortwave_radiation": [None], "temperature_2m": [None]}}
    out = parse_open_meteo(data)
    assert out["2026063005"] == (0.0, 25.0)


def test_provider_cache_lookup(monkeypatch):
    p = OpenMeteoSatelliteProvider()
    p._cache[(22.57, 88.36)] = parse_open_meteo(_SAMPLE)
    ghi, t = p.fetch(22.57, 88.36, datetime(2026, 6, 30, 5, tzinfo=timezone.utc))
    assert ghi == 780.0 and t == 35.0
