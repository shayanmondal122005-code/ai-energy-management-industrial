"""GHI → plane-of-array (POA) transposition via pvlib.

The satellite/forecast providers give GHI (horizontal). Panels are tilted, so we
transpose to POA using sun position + a GHI decomposition (Erbs) + the isotropic
sky transposition — exactly the pvlib pipeline. POA is the irradiance the modules
actually see and the driver of the baseline engine.

Kept dependency-isolated: if pvlib/pandas are unavailable or error on a sample,
`ghi_to_poa` falls back to a cosine-projection estimate so the pipeline never
hard-fails on a single bad timestamp.
"""
from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def ghi_to_poa(ghi_wm2: float, ts: datetime, lat: float, lon: float,
               tilt_deg: float, azimuth_deg: float) -> float:
    """Transpose horizontal GHI to plane-of-array global irradiance (W/m²).

    Returns 0 at night (sun below horizon). Uses pvlib (solar position → Erbs
    decomposition → isotropic transposition); falls back to a tilt-cosine estimate
    if pvlib is missing or raises.
    """
    ghi = max(0.0, float(ghi_wm2))
    if ghi <= 0:
        return 0.0
    try:
        import pandas as pd
        import pvlib

        idx = pd.DatetimeIndex([pd.Timestamp(ts)])
        solpos = pvlib.solarposition.get_solarposition(idx, lat, lon)
        zenith = float(solpos["apparent_zenith"].iloc[0])
        sun_az = float(solpos["azimuth"].iloc[0])
        if zenith >= 90.0:
            return 0.0
        erbs = pvlib.irradiance.erbs(ghi, zenith, idx)
        dni = float(erbs["dni"].iloc[0])
        dhi = float(erbs["dhi"].iloc[0])
        poa = pvlib.irradiance.get_total_irradiance(
            surface_tilt=tilt_deg, surface_azimuth=azimuth_deg,
            solar_zenith=zenith, solar_azimuth=sun_az,
            dni=dni, ghi=ghi, dhi=dhi,
        )["poa_global"]
        val = float(poa.iloc[0] if hasattr(poa, "iloc") else poa)
        if val != val or val < 0:  # NaN guard
            raise ValueError("non-finite POA")
        return val
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("pvlib transposition failed (%s) — cosine fallback", exc)
        return _cosine_fallback(ghi, ts, lat, tilt_deg)


def clearsky_ghi(ts: datetime, lat: float, lon: float) -> float:
    """Clear-sky GHI (W/m²) at a timestamp via pvlib (Ineichen). Used to measure how
    cloudy a forecast hour is (clearness = forecast GHI / clear-sky GHI). 0 at night
    or if pvlib is unavailable."""
    try:
        import pandas as pd
        import pvlib

        idx = pd.DatetimeIndex([pd.Timestamp(ts)])
        loc = pvlib.location.Location(lat, lon)
        return float(loc.get_clearsky(idx)["ghi"].iloc[0])
    except Exception:  # pragma: no cover - defensive
        return 0.0


def _cosine_fallback(ghi_wm2: float, ts: datetime, lat: float, tilt_deg: float) -> float:
    """Coarse tilt gain when pvlib is unavailable: scale GHI by the ratio of tilted
    to horizontal projection at solar noon. Intentionally simple — a safety net."""
    import math

    # Solar declination (deg) by day-of-year (Cooper).
    doy = ts.timetuple().tm_yday
    decl = 23.45 * math.sin(math.radians(360.0 * (284 + doy) / 365.0))
    noon_elev = 90.0 - abs(lat - decl)
    if noon_elev <= 0:
        return 0.0
    gain = math.cos(math.radians(max(0.0, (lat - decl)) - tilt_deg)) / max(
        0.2, math.sin(math.radians(noon_elev)))
    return max(0.0, ghi_wm2 * min(1.6, max(0.6, gain)))
