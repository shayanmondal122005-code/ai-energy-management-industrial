"""Server-side irradiance & weather — NO physical sensor on site.

EnvironmentSource.get(plant, ts) → EnvSample {poa, ambient, ghi}. The concrete
SatelliteSource pulls GHI + ambient for the plant's lat/lon from a MODELED provider
(Solcast/Solargis/NASA-style — swappable behind SatelliteProvider) and transposes
GHI → POA with pvlib. Results cache in the `env` table keyed by (plant, ts) so we
never refetch the same interval.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Protocol

from backend.services.solar_om.irradiance import ghi_to_poa
from backend.services.solar_om.models import EnvSample, EnvSource, Plant

logger = logging.getLogger(__name__)


class EnvCache(Protocol):
    """(plant, ts, source) → EnvSample cache. DB-backed impl lives in app/db."""
    def get(self, plant_id: str, ts: datetime, source: EnvSource) -> EnvSample | None: ...
    def put(self, sample: EnvSample) -> None: ...


class NullEnvCache:
    def get(self, plant_id, ts, source):  # noqa: D401
        return None

    def put(self, sample):
        return None


class EnvironmentSource(ABC):
    @abstractmethod
    def get(self, plant: Plant, ts: datetime) -> EnvSample:
        ...


class SatelliteProvider(ABC):
    """Raw modeled GHI + ambient for a lat/lon at a timestamp. Swap concrete
    backends (Solcast / Solargis / NASA POWER) without touching SatelliteSource."""

    @abstractmethod
    def fetch(self, lat: float, lon: float, ts: datetime) -> tuple[float, float]:
        """Return (ghi_wm2, ambient_temp_c)."""
        ...


class HttpSatelliteProvider(SatelliteProvider):
    """Config-driven HTTP adapter. The exact JSON field paths differ per vendor,
    so URL + auth + the two response keys are configuration, not code.

    TODO(wire-provider): set base_url / api_key / field paths for your chosen
    satellite provider (Solcast estimated_actuals, Solargis, NASA POWER, …).
    """
    def __init__(self, base_url: str, api_key: str | None = None, *,
                 ghi_field: str = "ghi", temp_field: str = "air_temp",
                 timeout_s: float = 5.0):
        self.base_url = base_url
        self.api_key = api_key
        self.ghi_field = ghi_field
        self.temp_field = temp_field
        self.timeout_s = timeout_s

    def fetch(self, lat: float, lon: float, ts: datetime) -> tuple[float, float]:
        import httpx

        params = {"latitude": lat, "longitude": lon, "time": ts.isoformat()}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        r = httpx.get(self.base_url, params=params, headers=headers, timeout=self.timeout_s)
        r.raise_for_status()
        data = r.json()
        return float(data[self.ghi_field]), float(data[self.temp_field])


def parse_power_hourly(data: dict) -> dict[str, tuple[float, float]]:
    """NASA POWER hourly JSON → {'YYYYMMDDHH' (UTC): (ghi_wm2, ambient_c)}.

    ALLSKY_SFC_SW_DWN is reported as Wh/m² per hour, numerically the W/m² mean over
    that hour, so it is used directly as GHI. Missing values (-999) become 0 GHI /
    25 °C. Pure function (no network) so it unit-tests against a captured response.
    """
    p = data["properties"]["parameter"]
    ghi_map = p["ALLSKY_SFC_SW_DWN"]
    t2m_map = p.get("T2M", {})
    out: dict[str, tuple[float, float]] = {}
    for k, g in ghi_map.items():
        gv = 0.0 if g is None or g == -999.0 else max(0.0, float(g))
        t = t2m_map.get(k)
        tv = 25.0 if t is None or t == -999.0 else float(t)
        out[k] = (gv, tv)
    return out


class NasaPowerProvider(SatelliteProvider):
    """NASA POWER — free, no API key, satellite-derived (CERES/MERRA-2), global incl.
    India. Best for HISTORICAL irradiance (radiation lags the present by a few days),
    which is exactly the data needed to backtest the dip against an existing dataset.
    One HTTP call per (lat, lon, day) is cached and serves all 24 hours.
    """
    BASE = "https://power.larc.nasa.gov/api/temporal/hourly/point"

    def __init__(self, timeout_s: float = 30.0):
        self.timeout_s = timeout_s
        self._cache: dict[tuple, dict[str, tuple[float, float]]] = {}

    def _fetch_day(self, lat: float, lon: float, day: str) -> dict[str, tuple[float, float]]:
        import httpx

        params = {"parameters": "ALLSKY_SFC_SW_DWN,T2M", "latitude": lat, "longitude": lon,
                  "start": day, "end": day, "format": "JSON", "community": "RE",
                  "time-standard": "UTC"}
        r = httpx.get(self.BASE, params=params, timeout=self.timeout_s)
        r.raise_for_status()
        return parse_power_hourly(r.json())

    def fetch(self, lat: float, lon: float, ts: datetime) -> tuple[float, float]:
        from datetime import timezone as _tz
        u = ts.astimezone(_tz.utc)
        day = u.strftime("%Y%m%d")
        key = (round(lat, 3), round(lon, 3), day)
        if key not in self._cache:
            self._cache[key] = self._fetch_day(lat, lon, day)
        return self._cache[key].get(u.strftime("%Y%m%d%H"), (0.0, 25.0))


def parse_open_meteo(data: dict) -> dict[str, tuple[float, float]]:
    """Open-Meteo hourly JSON → {'YYYYMMDDHH' (UTC): (ghi_wm2, ambient_c)}. Pure."""
    h = data["hourly"]
    times = h["time"]
    ghi = h.get("shortwave_radiation", [])
    temp = h.get("temperature_2m", [])
    out: dict[str, tuple[float, float]] = {}
    for i, tstr in enumerate(times):
        key = tstr.replace("-", "").replace("T", "").replace(":", "")[:10]  # YYYYMMDDHH
        g = ghi[i] if i < len(ghi) and ghi[i] is not None else 0.0
        t = temp[i] if i < len(temp) and temp[i] is not None else 25.0
        out[key] = (max(0.0, float(g)), float(t))
    return out


class OpenMeteoSatelliteProvider(SatelliteProvider):
    """Low-latency GHI + ambient from Open-Meteo (free, no key). Unlike NASA POWER
    (radiation lags days) this has recent + forecast hours, so it drives NEAR-REAL-TIME
    detection. One fetch per (lat, lon) caches a window of past + forecast days."""
    BASE = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, timeout_s: float = 10.0, past_days: int = 7):
        self.timeout_s = timeout_s
        self.past_days = past_days
        self._cache: dict[tuple, dict[str, tuple[float, float]]] = {}

    def fetch(self, lat: float, lon: float, ts: datetime) -> tuple[float, float]:
        from datetime import timezone as _tz
        key = (round(lat, 3), round(lon, 3))
        if key not in self._cache:
            import httpx
            r = httpx.get(self.BASE, params={
                "latitude": lat, "longitude": lon,
                "hourly": "shortwave_radiation,temperature_2m",
                "past_days": self.past_days, "forecast_days": 2, "timezone": "UTC",
            }, timeout=self.timeout_s)
            r.raise_for_status()
            self._cache[key] = parse_open_meteo(r.json())
        return self._cache[key].get(ts.astimezone(_tz.utc).strftime("%Y%m%d%H"), (0.0, 25.0))


class SatelliteSource(EnvironmentSource):
    """GHI+ambient from a provider → POA via pvlib → cached EnvSample."""

    def __init__(self, provider: SatelliteProvider, cache: EnvCache | None = None):
        self.provider = provider
        self.cache = cache or NullEnvCache()

    def get(self, plant: Plant, ts: datetime) -> EnvSample:
        cached = self.cache.get(plant.id, ts, EnvSource.SATELLITE)
        if cached is not None:
            return cached
        ghi, ambient = self.provider.fetch(plant.lat, plant.lon, ts)
        poa = ghi_to_poa(ghi, ts, plant.lat, plant.lon, plant.tilt_deg, plant.azimuth_deg)
        sample = EnvSample(ts=ts, plant_id=plant.id, poa_wm2=poa, ambient_temp_c=ambient,
                           ghi_wm2=ghi, source=EnvSource.SATELLITE)
        self.cache.put(sample)
        return sample


class MockEnvironment(EnvironmentSource):
    """Deterministic env for tests — a clear-sky GHI bell curve with optional
    cloud dips injected at specific timestamps (shared driver for cloud_pass)."""

    def __init__(self, clear_sky_peak_ghi: float = 900.0, ambient_c: float = 30.0,
                 cloud_intervals: set[datetime] | None = None, cloud_factor: float = 0.25):
        self.peak = clear_sky_peak_ghi
        self.ambient = ambient_c
        self.cloud_intervals = cloud_intervals or set()
        self.cloud_factor = cloud_factor

    def clear_sky_ghi(self, ts: datetime) -> float:
        import math
        h = ts.hour + ts.minute / 60.0
        if h < 6 or h > 18:
            return 0.0
        return self.peak * max(0.0, math.sin((h - 6) / 12.0 * math.pi))

    def get(self, plant: Plant, ts: datetime) -> EnvSample:
        ghi = self.clear_sky_ghi(ts)
        if ts in self.cloud_intervals:
            ghi *= self.cloud_factor  # a cloud passes — GHI drops site-wide
        poa = ghi_to_poa(ghi, ts, plant.lat, plant.lon, plant.tilt_deg, plant.azimuth_deg)
        return EnvSample(ts=ts, plant_id=plant.id, poa_wm2=poa, ambient_temp_c=self.ambient,
                         ghi_wm2=ghi, source=EnvSource.SATELLITE)
