"""NASA POWER provider — parser is unit-tested against a captured response shape
(no network in CI). The live HTTP path is exercised manually + by the compare demo.
"""
from datetime import datetime, timezone

from backend.services.solar_om.environment import NasaPowerProvider, parse_power_hourly

# Trimmed real-shape POWER response (Kolkata, a clear historical day).
_SAMPLE = {
    "properties": {"parameter": {
        "ALLSKY_SFC_SW_DWN": {
            "2024031500": 0.0, "2024031503": 475.73, "2024031505": 787.83,
            "2024031509": 191.73, "2024031518": -999.0,   # -999 = missing
        },
        "T2M": {
            "2024031500": 24.1, "2024031503": 27.4, "2024031505": 31.2,
            "2024031509": 33.0, "2024031518": -999.0,
        },
    }},
    "parameters": {"ALLSKY_SFC_SW_DWN": {"units": "Wh/m^2"}},
}


class TestParse:
    def test_maps_hours_to_ghi_temp(self):
        out = parse_power_hourly(_SAMPLE)
        assert out["2024031505"] == (787.83, 31.2)        # peak hour
        assert out["2024031500"][0] == 0.0                # night

    def test_missing_becomes_zero_ghi_default_temp(self):
        out = parse_power_hourly(_SAMPLE)
        assert out["2024031518"] == (0.0, 25.0)           # -999 → (0 GHI, 25 °C)


class TestProviderCaching:
    def test_fetch_uses_day_cache(self, monkeypatch):
        calls = {"n": 0}

        def fake_fetch_day(self, lat, lon, day):
            calls["n"] += 1
            return parse_power_hourly(_SAMPLE)

        monkeypatch.setattr(NasaPowerProvider, "_fetch_day", fake_fetch_day)
        p = NasaPowerProvider()
        ts5 = datetime(2024, 3, 15, 5, tzinfo=timezone.utc)
        ts9 = datetime(2024, 3, 15, 9, tzinfo=timezone.utc)
        assert p.fetch(22.57, 88.36, ts5) == (787.83, 31.2)
        assert p.fetch(22.57, 88.36, ts9) == (191.73, 33.0)
        assert calls["n"] == 1     # both hours served from ONE day fetch
