"""Tests for the irradiance-based solar forecast (pure conversion math)."""
import math

from backend.services.solar_forecast import (
    ac_power_kw,
    cell_temperature,
    forecast_from_series,
)


class TestCellTemperature:
    def test_equals_air_temp_in_darkness(self):
        assert cell_temperature(0, 30.0) == 30.0

    def test_hotter_than_air_in_sun(self):
        # NOCT 45: at 800 W/m² cell is (45-20)/800*800 = 25°C above air.
        assert math.isclose(cell_temperature(800, 30.0), 55.0, abs_tol=1e-6)

    def test_monotonic_in_irradiance(self):
        assert cell_temperature(1000, 30) > cell_temperature(500, 30)


class TestAcPowerKw:
    def test_zero_at_night(self):
        assert ac_power_kw(0, 25, kwp=200) == 0.0

    def test_zero_without_array(self):
        assert ac_power_kw(800, 25, kwp=0) == 0.0

    def test_scales_with_kwp(self):
        assert math.isclose(ac_power_kw(800, 25, 400), 2 * ac_power_kw(800, 25, 200), rel_tol=1e-6)

    def test_stc_reference_with_losses(self):
        # At 1000 W/m² and a cell held to 25°C (temp_coeff=0): P = kWp*(1)*(1-loss).
        p = ac_power_kw(1000, 25, kwp=200, temp_coeff=0.0)
        assert math.isclose(p, 200 * 0.80, abs_tol=0.1)  # 20% default loss

    def test_heat_derates_output(self):
        # Same irradiance, hotter air → hotter cell → less power.
        cool = ac_power_kw(800, 20, kwp=200)
        hot = ac_power_kw(800, 45, kwp=200)
        assert hot < cool

    def test_clipped_to_nameplate(self):
        # Absurd irradiance with zero loss must still not exceed kWp.
        p = ac_power_kw(5000, 25, kwp=200, system_loss=0.0, temp_coeff=0.0)
        assert p <= 200


class TestForecastFromSeries:
    def test_returns_24_values(self):
        ghi = [0.0] * 6 + [200, 400, 600, 800, 900, 950, 900, 800, 600, 400, 200] + [0.0] * 7
        temp = [28.0] * 24
        out = forecast_from_series(ghi, temp, kwp=200)
        assert len(out) == 24

    def test_night_hours_zero(self):
        ghi = [0.0] * 24
        out = forecast_from_series(ghi, [30.0] * 24, kwp=200)
        assert all(v == 0.0 for v in out)

    def test_tracks_irradiance_shape(self):
        ghi = [0, 0, 0, 0, 0, 0, 100, 300, 500, 700, 850, 950, 950, 850, 700, 500, 300, 100, 0, 0, 0, 0, 0, 0]
        out = forecast_from_series(ghi, [28.0] * 24, kwp=200)
        assert out[11] == max(out)        # peak near solar noon (index 11/12)
        assert out[0] == 0.0

    def test_missing_temps_default_to_stc(self):
        # GHI-only feed (temps shorter) still yields a forecast.
        ghi = [500.0] * 24
        out = forecast_from_series(ghi, [], kwp=200)
        assert all(v > 0 for v in out)
