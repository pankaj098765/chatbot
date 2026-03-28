"""
admin/database/redis_client.py — Async Redis helpers for the admin dashboard.

Uses the same key namespaces as bot/database/redis_client.py.
"""
from __future__ import annotations

import redis.asyncio as aioredis

from admin.config import settings
from config.app_config import app_config

_redis: aioredis.Redis | None = None

QUEUE_KEY = "matchmaking_queue"
ADMIN_CONFIG_KEY = "admin:config"
QUEUE_STATS_KEY = "queue:stats"

_CONFIG_DEFAULTS: dict = {
    "fallback_rate": 0.10,
    "retry_limit": 3.0,
    "priority_boost": 0.0,
    "randomness_level": 0.5,
    # Seeded from app_config so language defaults reflect buyer's configuration
    "default_language": app_config.default_language,
    "allowed_languages": ",".join(app_config.allowed_languages),
    "default_chat_mode": app_config.default_chat_mode,
}


async def connect() -> None:
    global _redis
    _redis = aioredis.from_url(settings.redis_url, decode_responses=True)


async def disconnect() -> None:
    if _redis:
        await _redis.aclose()


def _r() -> aioredis.Redis:
    assert _redis is not None, "Redis not connected"
    return _redis


async def queue_size() -> int:
    return await _r().zcard(QUEUE_KEY)


async def get_gender_queue_stats() -> tuple[int, int]:
    """Return (male_count, female_count) from the Redis cache."""
    pipe = _r().pipeline()
    pipe.get("queue:gender:male")
    pipe.get("queue:gender:female")
    results = await pipe.execute()
    male = int(results[0]) if results[0] else 0
    female = int(results[1]) if results[1] else 0
    return male, female


async def get_queue_stats() -> dict:
    """Retrieve queue health stats persisted by the queue monitor."""
    raw = await _r().hgetall(QUEUE_STATS_KEY)
    result: dict = {}
    for k, v in raw.items():
        try:
            result[k] = float(v)
        except (ValueError, TypeError):
            result[k] = v
    return result


async def get_admin_config() -> dict:
    """Return the current admin config with defaults applied for missing keys."""
    raw = await _r().hgetall(ADMIN_CONFIG_KEY)
    config: dict = dict(_CONFIG_DEFAULTS)
    for k, v in raw.items():
        try:
            config[k] = float(v)
        except (ValueError, TypeError):
            config[k] = v
    return config


async def set_admin_config_bulk(mapping: dict[str, float]) -> None:
    """Persist multiple admin config values to Redis."""
    await _r().hset(ADMIN_CONFIG_KEY, mapping={k: str(v) for k, v in mapping.items()})
