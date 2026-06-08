"""
Load forecast service — the bridge between accumulated telemetry and the brain.

Today this is a seasonal-naive forecaster: average load per (sim) hour-of-day
learned from recent history. It exposes the SAME interface a trained XGBoost
model will use, so swapping in the ML model later is a drop-in change.

The brain calls get_load_forecast(); if `available` is False (not enough data
to be trustworthy) the brain falls back to reactive dispatch.
"""
import json
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import get_redis

logger = logging.getLogger(__name__)

# Guard thresholds — "trained well enough to trust"
MIN_SAMPLES = 150     # total readings
MIN_BUCKETS = 10      # distinct hours-of-day covered
CACHE_TTL   = 120     # seconds (sim is fast; recompute every 2 min)


async def get_load_forecast(db: AsyncSession, site_id: str, current_hour: float | None = None) -> dict:
    """Return a load forecast for the site. Cached in Redis.

    Shape:
      {
        "available": bool,        # True only when enough history to trust
        "method": "hourly-avg",   # later: "xgboost"
        "samples": int,
        "buckets": int,
        "predicted_peak_kw": float,
        "peak_hour": int,
        "peak_in_hours": float|None,
        "avg_next_3h_kw": float,
        "profile": {hour: kw}     # 0..23 where known
      }
    """
    # Try cache first
    try:
        r = await get_redis()
        cached = await r.get(f"forecast:{site_id}")
        if cached:
            f = json.loads(cached)
            # recompute "peak_in_hours" against the live current hour (cheap)
            if current_hour is not None and f.get("available"):
                f["peak_in_hours"] = _hours_until(current_hour, f["peak_hour"])
                f["avg_next_3h_kw"] = _avg_next_3h(f["profile"], current_hour)
            return f
    except Exception:
        r = None

    # Aggregate recent telemetry by sim hour-of-day
    try:
        rows = (await db.execute(
            text("""
                SELECT floor(sim_hour) AS hr, AVG(total_load_w) AS avg_w, COUNT(*) AS n
                FROM telemetry
                WHERE site_id = :sid
                  AND sim_hour IS NOT NULL
                  AND recorded_at > now() - interval '3 hours'
                GROUP BY floor(sim_hour)
                ORDER BY hr
            """),
            {"sid": site_id},
        )).fetchall()
    except Exception as exc:
        logger.warning("forecast query failed: %s", exc)
        rows = []

    profile = {int(r.hr): float(r.avg_w) / 1000.0 for r in rows if r.hr is not None}
    samples = sum(int(r.n) for r in rows)
    buckets = len(profile)

    available = samples >= MIN_SAMPLES and buckets >= MIN_BUCKETS

    if not available:
        result = {
            "available": False, "method": "hourly-avg",
            "samples": samples, "buckets": buckets,
            "predicted_peak_kw": 0.0, "peak_hour": -1,
            "peak_in_hours": None, "avg_next_3h_kw": 0.0, "profile": profile,
        }
    else:
        peak_hour = max(profile, key=profile.get)
        result = {
            "available": True, "method": "hourly-avg",
            "samples": samples, "buckets": buckets,
            "predicted_peak_kw": round(profile[peak_hour], 2),
            "peak_hour": peak_hour,
            "peak_in_hours": _hours_until(current_hour, peak_hour) if current_hour is not None else None,
            "avg_next_3h_kw": _avg_next_3h(profile, current_hour) if current_hour is not None else 0.0,
            "profile": {str(k): round(v, 2) for k, v in profile.items()},
        }

    try:
        if r:
            await r.setex(f"forecast:{site_id}", CACHE_TTL, json.dumps(result))
    except Exception:
        pass
    return result


def _hours_until(now_h: float, target_h: int) -> float:
    d = (target_h - now_h) % 24
    return round(d, 1)


def _avg_next_3h(profile: dict, now_h: float | None) -> float:
    if now_h is None or not profile:
        return 0.0
    prof = {int(k): float(v) for k, v in profile.items()}
    vals = []
    for k in range(1, 4):
        h = int((now_h + k) % 24)
        if h in prof:
            vals.append(prof[h])
    return round(sum(vals) / len(vals), 2) if vals else 0.0
