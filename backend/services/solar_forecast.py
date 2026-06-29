"""Irradiance-based 24h solar generation forecast.

Replaces the crude clear-sky sine curve with a forecast driven by REAL predicted
irradiance from Open-Meteo (the same free API solar_health already uses). The
dominant driver of PV output is plane irradiance, so a GHI-driven model tracks
clouds, monsoon, and seasonality far better than a fixed sine × month-factor.

Physics (STC-referenced single-diode-free yield model — no PVLib dependency):

    T_cell = T_air + (NOCT − 20)/800 × GHI          (NOCT cell-temp model)
    P_ac   = kWp × (GHI / 1000)                      (linear in irradiance, ref STC)
                 × (1 − system_loss)                  (inverter + wiring + mismatch + soiling)
                 × [1 + γ × (T_cell − 25)]            (temperature derate, γ ≈ −0.004/°C)
    P_ac   = clip(P_ac, 0, kWp)                       (cannot exceed nameplate AC)

This is the widely-used "simple" PV estimate. It is honest about its scope: it
uses horizontal GHI (the value Open-Meteo forecasts directly) rather than a full
plane-of-array transposition from tilt/azimuth + solar geometry — that is the
documented next refinement, not silently assumed here.

Pure functions (cell_temperature, ac_power_kw, forecast_from_series) unit-test
without a network; fetch_open_meteo_ghi does the I/O and is kept thin + optional.
"""
import logging

logger = logging.getLogger(__name__)

N = 24

# Defaults for a typical rooftop/ground C&I array in India.
DEFAULT_SYSTEM_LOSS = 0.20    # 20% total system losses (inverter, wiring, mismatch, light soiling)
DEFAULT_TEMP_COEFF = -0.004   # −0.4%/°C for crystalline silicon Pmax
DEFAULT_NOCT_C = 45.0         # nominal operating cell temperature (typical module spec)
STC_IRRADIANCE = 1000.0       # W/m² reference


def cell_temperature(ghi_wm2: float, air_temp_c: float, noct_c: float = DEFAULT_NOCT_C) -> float:
    """Module cell temperature via the NOCT model: hotter in strong sun than the air."""
    return air_temp_c + (noct_c - 20.0) / 800.0 * max(0.0, float(ghi_wm2))


def ac_power_kw(
    ghi_wm2: float,
    air_temp_c: float,
    kwp: float,
    *,
    system_loss: float = DEFAULT_SYSTEM_LOSS,
    temp_coeff: float = DEFAULT_TEMP_COEFF,
    noct_c: float = DEFAULT_NOCT_C,
) -> float:
    """AC power (kW) for one hour from predicted GHI and air temperature.

    Linear in irradiance referenced to STC (1000 W/m²), derated for system losses
    and cell temperature, clipped to nameplate AC (kWp).
    """
    ghi = max(0.0, float(ghi_wm2))
    kwp = max(0.0, float(kwp))
    if ghi <= 0 or kwp <= 0:
        return 0.0
    t_cell = cell_temperature(ghi, air_temp_c, noct_c)
    temp_derate = 1.0 + temp_coeff * (t_cell - 25.0)
    p = kwp * (ghi / STC_IRRADIANCE) * (1.0 - system_loss) * max(0.0, temp_derate)
    return round(min(max(0.0, p), kwp), 2)


def forecast_from_series(
    ghi_series: list[float],
    temp_series: list[float],
    kwp: float,
    *,
    system_loss: float = DEFAULT_SYSTEM_LOSS,
    temp_coeff: float = DEFAULT_TEMP_COEFF,
    noct_c: float = DEFAULT_NOCT_C,
) -> list[float]:
    """Map aligned 24h GHI + air-temperature series to a 24h AC kW forecast.

    The two series must already be ordered for the next 24 hours (index 0 = the
    current hour). Missing temperatures default to 25 °C (STC), so a GHI-only feed
    still produces a usable forecast.
    """
    out = []
    for h in range(N):
        ghi = ghi_series[h] if h < len(ghi_series) and ghi_series[h] is not None else 0.0
        temp = temp_series[h] if h < len(temp_series) and temp_series[h] is not None else 25.0
        out.append(ac_power_kw(
            ghi, temp, kwp,
            system_loss=system_loss, temp_coeff=temp_coeff, noct_c=noct_c,
        ))
    return out


def fetch_open_meteo_ghi(lat: float, lon: float, hour_now: int, timezone: str = "Asia/Kolkata"):
    """Fetch the next-24h GHI + air-temp forecast from Open-Meteo, aligned to hour_now.

    Returns (ghi_series, temp_series) of length 24, or (None, None) on any failure —
    the caller falls back to the clear-sky estimate. Network I/O is isolated here so
    the conversion math stays unit-testable.
    """
    try:
        import requests

        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "hourly": "shortwave_radiation,temperature_2m",
                "forecast_days": 2, "timezone": timezone,
            },
            timeout=5,
        )
        if r.status_code != 200:
            return None, None
        hourly = r.json()["hourly"]
        ghi_all = hourly["shortwave_radiation"]
        temp_all = hourly["temperature_2m"]
        # Open-Meteo hourly arrays start at 00:00 local today; slice the next 24h.
        start = max(0, int(hour_now))
        ghi = ghi_all[start:start + N]
        temp = temp_all[start:start + N]
        if len(ghi) < N:  # near end of horizon — pad with the tail of day-2
            ghi = (ghi + ghi_all[:N])[:N]
            temp = (temp + temp_all[:N])[:N]
        return ghi, temp
    except Exception as exc:
        logger.warning("Open-Meteo GHI fetch failed (%s) — caller will fall back", exc)
        return None, None
