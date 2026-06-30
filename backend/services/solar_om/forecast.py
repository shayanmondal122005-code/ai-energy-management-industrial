"""Forecast provider — our EXISTING in-house EMS forecast service.

ForecastProvider.get(plant, ts_window) → ForecastWindow with a look-ahead POA
series, a cloud_variability_index (0 clear … 1 highly broken), and a clear_sky_flag.
The environmental gate uses these to widen/tighten thresholds and to pick clean
clear-sky days for eta_bos calibration.
"""
from __future__ import annotations

import logging
import statistics
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

from backend.services.solar_om.irradiance import clearsky_ghi, ghi_to_poa
from backend.services.solar_om.models import ForecastWindow, Plant

logger = logging.getLogger(__name__)

# Std of clearness that maps to a fully "variable" (broken-cloud) sky.
_VARIABILITY_FULL_SCALE = 0.33


def derive_variability(clearness_ratios: list[float]) -> tuple[float, bool]:
    """From daylight clearness (= forecast GHI / clear-sky GHI) derive the two signals
    the gate uses: cloud_variability_index (0 = dead clear … 1 = highly broken cloud)
    and clear_sky_flag. A clear day has near-constant clearness ≈ 1 (low std); a broken
    sky swings wildly (high std). Pure + unit-tested."""
    vals = [max(0.0, min(1.2, r)) for r in clearness_ratios]
    if not vals:
        return 0.0, False
    if len(vals) == 1:
        return 0.0, vals[0] >= 0.85
    mean = statistics.fmean(vals)
    cvi = min(1.0, statistics.pstdev(vals) / _VARIABILITY_FULL_SCALE)
    clear = mean >= 0.85 and cvi <= 0.2
    return round(cvi, 3), clear


def forecast_from_ghi(plant: Plant, ts_start: datetime, times: list[datetime],
                      ghi_series: list[float]) -> ForecastWindow:
    """Build a ForecastWindow from a GHI series (forecast OR real historical satellite):
    transpose to POA and measure clearness vs pvlib clear-sky to derive variability."""
    poa = [ghi_to_poa(g, t, plant.lat, plant.lon, plant.tilt_deg, plant.azimuth_deg)
           for t, g in zip(times, ghi_series)]
    clearness = []
    for t, g in zip(times, ghi_series):
        cs = clearsky_ghi(t, plant.lat, plant.lon)
        if cs > 50.0:                       # daylight only
            clearness.append(max(0.0, g) / cs)
    cvi, clear = derive_variability(clearness)
    return ForecastWindow(plant_id=plant.id, ts_start=ts_start, poa_forecast_wm2=poa,
                          cloud_variability_index=cvi, clear_sky_flag=clear)


class ForecastProvider(ABC):
    @abstractmethod
    def get(self, plant: Plant, ts_start: datetime, hours: int) -> ForecastWindow:
        ...

    def clear_sky_flag(self, plant: Plant, ts: datetime) -> bool:
        return self.get(plant, ts, 1).clear_sky_flag


class OpenMeteoForecast(ForecastProvider):
    """Concrete, reachable forecast — Open-Meteo hourly shortwave_radiation (free, no
    key). The in-house EMS forecast is Open-Meteo-based, so this mirrors what the EMS
    produces; swap EmsForecastAdapter in once the EMS exposes its own endpoint."""
    BASE = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, timeout_s: float = 10.0):
        self.timeout_s = timeout_s

    def get(self, plant: Plant, ts_start: datetime, hours: int) -> ForecastWindow:
        import httpx

        days = min(7, max(1, (ts_start.hour + max(1, hours)) // 24 + 1))
        r = httpx.get(self.BASE, params={
            "latitude": plant.lat, "longitude": plant.lon,
            "hourly": "shortwave_radiation", "forecast_days": days, "timezone": "UTC",
        }, timeout=self.timeout_s)
        r.raise_for_status()
        h = r.json()["hourly"]
        times = [datetime.fromisoformat(s).replace(tzinfo=timezone.utc) for s in h["time"]]
        ghi = [float(x) if x is not None else 0.0 for x in h["shortwave_radiation"]]
        start = next((i for i, t in enumerate(times) if t >= ts_start), 0)
        return forecast_from_ghi(plant, ts_start, times[start:start + hours],
                                 ghi[start:start + hours])


class EmsForecastAdapter(ForecastProvider):
    """Thin client to OUR existing EMS forecast service.

    TODO(wire-ems): point base_url/auth at the EMS forecast endpoint and map its
    response → ForecastWindow. The EMS already returns an irradiance/solar forecast;
    derive cloud_variability_index from its inter-hour variance and clear_sky_flag
    from its clear-sky ratio. Until wired, this raises so misconfiguration is loud.
    """
    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 timeout_s: float = 5.0):
        self.base_url = base_url
        self.api_key = api_key
        self.timeout_s = timeout_s

    def get(self, plant: Plant, ts_start: datetime, hours: int) -> ForecastWindow:
        if not self.base_url:
            raise RuntimeError(
                "EmsForecastAdapter not wired — set EMS_FORECAST_URL (see TODO(wire-ems))")
        import httpx  # pragma: no cover - exercised once EMS is wired

        params = {"plant_id": plant.id, "start": ts_start.isoformat(), "hours": hours}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        r = httpx.get(f"{self.base_url}/forecast", params=params, headers=headers,
                      timeout=self.timeout_s)
        r.raise_for_status()
        d = r.json()
        # TODO(wire-ems): adapt these field names to the EMS response shape.
        ghi_series = [float(x) for x in d["poa_forecast_wm2"]]
        return ForecastWindow(
            plant_id=plant.id, ts_start=ts_start, poa_forecast_wm2=ghi_series,
            cloud_variability_index=float(d.get("cloud_variability_index", 0.0)),
            clear_sky_flag=bool(d.get("clear_sky_flag", False)),
        )


class MockForecast(ForecastProvider):
    """Scripted forecast for tests. Emits a clear window by default; mark specific
    days/intervals as high-variability (cloud) windows on demand."""

    def __init__(self, peak_ghi: float = 900.0, *, variable: bool = False,
                 variability_index: float = 0.7,
                 variable_intervals: set[datetime] | None = None):
        self.peak = peak_ghi
        self.variable = variable
        self.variability_index = variability_index
        self.variable_intervals = variable_intervals or set()

    def _clear_ghi(self, ts: datetime) -> float:
        import math
        h = ts.hour + ts.minute / 60.0
        if h < 6 or h > 18:
            return 0.0
        return self.peak * max(0.0, math.sin((h - 6) / 12.0 * math.pi))

    def get(self, plant: Plant, ts_start: datetime, hours: int) -> ForecastWindow:
        series = []
        is_variable = self.variable or ts_start in self.variable_intervals
        for i in range(max(1, hours)):
            ts = ts_start + timedelta(hours=i)
            series.append(ghi_to_poa(self._clear_ghi(ts), ts, plant.lat, plant.lon,
                                     plant.tilt_deg, plant.azimuth_deg))
        cvi = self.variability_index if is_variable else 0.05
        return ForecastWindow(plant_id=plant.id, ts_start=ts_start,
                              poa_forecast_wm2=series,
                              cloud_variability_index=cvi,
                              clear_sky_flag=not is_variable)
