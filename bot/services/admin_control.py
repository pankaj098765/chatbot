"""
bot/services/admin_control.py — Admin Control Panel (backend, no UI required).

# NEW

Stores runtime configuration in Redis under the admin:config hash.
All values are persisted so they survive restarts and take effect immediately
across all services that read them.

Config keys
-----------
fallback_rate    float  — baseline probability of routing to fallback  (default 0.10)
retry_limit      int    — max matchmaking retry attempts before fallback (default 3)
priority_boost   int    — flat extra priority added to every enqueue score (default 0)
randomness_level float  — controls delay/variation spread: 0.3 (low) → 0.7 (high)
                          (default 0.5)

Usage
-----
    config = await get_config()
    await update_config("randomness_level", 0.4)
    await update_config_bulk({"fallback_rate": 0.15, "retry_limit": 4})
"""
from __future__ import annotations

from bot.database import redis_client as redis

_DEFAULTS: dict[str, float] = {
    "fallback_rate": 0.10,
    "retry_limit": 3.0,
    "priority_boost": 0.0,
    "randomness_level": 0.5,
}


async def get_config() -> dict:
    """
    Return the current admin config with defaults applied for missing keys.
    All numeric values are returned as floats.
    """
    raw = await redis.get_admin_config_raw()
    config: dict = dict(_DEFAULTS)
    for k, v in raw.items():
        try:
            config[k] = float(v)
        except (ValueError, TypeError):
            config[k] = v
    return config


async def update_config(key: str, value: object) -> None:
    """Update a single admin config key in Redis."""
    await redis.set_admin_config_value(key, value)


async def update_config_bulk(updates: dict) -> None:
    """Update multiple admin config keys at once."""
    await redis.set_admin_config_bulk(updates)
