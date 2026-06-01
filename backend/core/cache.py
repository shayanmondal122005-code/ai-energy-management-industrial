import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis


async def ping_redis() -> bool:
    try:
        r = await get_redis()
        return await r.ping()
    except Exception:
        return False


# ── Generic cache helpers ───────────────────────────────────

async def cache_get(key: str) -> Optional[Any]:
    try:
        r = await get_redis()
        val = await r.get(key)
        if val is None:
            return None
        return json.loads(val)
    except Exception as exc:
        logger.warning("Redis get failed for key %s: %s", key, exc)
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> bool:
    try:
        r = await get_redis()
        await r.setex(key, ttl_seconds, json.dumps(value, default=str))
        return True
    except Exception as exc:
        logger.warning("Redis set failed for key %s: %s", key, exc)
        return False


async def cache_delete(key: str) -> bool:
    try:
        r = await get_redis()
        await r.delete(key)
        return True
    except Exception as exc:
        logger.warning("Redis delete failed for key %s: %s", key, exc)
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """Delete all keys matching a pattern. Use sparingly."""
    try:
        r = await get_redis()
        keys = await r.keys(pattern)
        if keys:
            return await r.delete(*keys)
        return 0
    except Exception as exc:
        logger.warning("Redis delete_pattern failed for %s: %s", pattern, exc)
        return 0


# ── Typed cache key builders ────────────────────────────────

def key_history_csv(facility_id: str, hours: int) -> str:
    return f"history_csv:{facility_id}:{hours}"


def key_solar_health(facility_id: str) -> str:
    return f"solar_health:{facility_id}"


def key_grid_state(facility_id: str) -> str:
    return f"grid_state:{facility_id}"


def key_weather(lat: float, lon: float) -> str:
    return f"weather:{lat:.2f}:{lon:.2f}"


def key_tariff(state: str) -> str:
    return f"tariff:{state}"


def key_model(facility_id: str) -> str:
    return f"model:{facility_id}"
