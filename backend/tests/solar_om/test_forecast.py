"""Forecast derivation — clearness → cloud_variability_index + clear_sky_flag.

Pure function, network-free. The live OpenMeteoForecast HTTP path is verified manually.
"""
from backend.services.solar_om.forecast import MockForecast, derive_variability
from backend.services.solar_om.models import Plant


class TestDeriveVariability:
    def test_clear_sky_low_variability(self):
        # Near-constant clearness ≈ 1.0 → a clear day.
        cvi, clear = derive_variability([0.98, 1.0, 0.99, 1.0, 0.98, 0.99])
        assert cvi < 0.2 and clear is True

    def test_broken_cloud_high_variability(self):
        # Clearness swinging wildly → broken cloud, not clear.
        cvi, clear = derive_variability([0.2, 1.0, 0.3, 0.95, 0.25, 0.9])
        assert cvi > 0.5 and clear is False

    def test_dim_but_steady_is_not_clear(self):
        # Steadily overcast (low clearness, low variability) → not clear, low cvi.
        cvi, clear = derive_variability([0.45, 0.47, 0.44, 0.46])
        assert clear is False

    def test_empty_is_safe(self):
        assert derive_variability([]) == (0.0, False)


class TestMockForecastStillWorks:
    def test_clear_vs_variable(self):
        plant = Plant(id="P", name="t", lat=22.57, lon=88.36, tilt_deg=22, azimuth_deg=180,
                      rated_capacity_kwp=100)
        from datetime import datetime, timezone
        ts = datetime(2026, 6, 29, 6, tzinfo=timezone.utc)
        assert MockForecast(variable=False).get(plant, ts, 6).clear_sky_flag is True
        assert MockForecast(variable=True).get(plant, ts, 6).clear_sky_flag is False
