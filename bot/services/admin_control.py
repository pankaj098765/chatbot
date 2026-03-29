"""
bot/services/admin_control.py — Admin Control Panel (backend, no UI required).

# NEW

Stores runtime configuration in Redis under the admin:config hash.
All values are persisted so they survive restarts and take effect immediately
across all services that read them.

Config keys
-----------
fallback_rate      float  — baseline probability of routing to fallback  (default 0.10)
retry_limit        int    — max matchmaking retry attempts before fallback (default 3)
priority_boost     int    — flat extra priority added to every enqueue score (default 0)
randomness_level   float  — controls delay/variation spread: 0.3 (low) → 0.7 (high)
                            (default 0.5)
language_mode      str    — "english" | "native" | "mixed"                # UPDATED
                            Controls how the entire bot speaks to all users.
                            english → English only
                            native  → native_language only
                            mixed   → mix of English + native_language
native_language    str    — ISO 639-1 code for the native language         # UPDATED
                            e.g. "hi" (Hindi), "es" (Spanish), "fr" (French)
                            Used when language_mode is "native" or "mixed".
ui_language        str    — ISO 639-1 code used for UI strings (buttons/menus).
                            Defaults to derived value from language_mode+native_language.
chat_language      str    — ISO 639-1 code the LLM/AI uses for response generation.
                            Defaults to native_language.

Usage
-----
    config = await get_config()
    await update_config("randomness_level", 0.4)
    await update_config_bulk({"fallback_rate": 0.15, "retry_limit": 4})
    await update_config_bulk({"language_mode": "native", "native_language": "hi"})

First-run setup
---------------
On the first call to get_config() after a fresh deployment (Redis has no stored
config), the English Mode preset is automatically applied and setup instructions
are logged to help buyers get started.
"""
from __future__ import annotations

import logging

from bot.database import redis_client as redis
from config.app_config import app_config

logger = logging.getLogger(__name__)

_DEFAULTS: dict[str, object] = {
    "fallback_rate": 0.10,
    "retry_limit": 3.0,
    "priority_boost": 0.0,
    "randomness_level": 0.5,
    # UPDATED: seeded from app_config so buyer's config.json / .env takes effect immediately
    "language_mode": app_config.language_mode,
    "native_language": app_config.native_language,
    # Separate channels: UI strings vs AI language
    "ui_language": app_config.ui_language,
    "chat_language": app_config.chat_language,
}

# ─── Language presets (mirrored from config_routes to avoid circular imports) ──

_LANGUAGE_PRESETS: dict[str, dict[str, str]] = {
    "english": {
        "language_mode": "english",
        "native_language": "en",
        "ui_language": "en",
        "chat_language": "en",
    },
    "spanish": {
        "language_mode": "native",
        "native_language": "es",
        "ui_language": "es",
        "chat_language": "es",
    },
    "hindi": {
        "language_mode": "native",
        "native_language": "hi",
        "ui_language": "hi",
        "chat_language": "hi",
    },
}

_DEFAULT_PRESET = "english"

# Sentinel key written to Redis to mark that first-run setup has completed.
_SETUP_DONE_KEY = "admin:config:setup_done"


async def _first_run_setup() -> None:
    """
    Apply the default language preset and log setup instructions when no
    admin configuration exists in Redis yet.  Runs once per deployment.
    """
    preset = _LANGUAGE_PRESETS[_DEFAULT_PRESET]
    await redis.set_admin_config_bulk(preset)
    await redis.set_admin_config_value(_SETUP_DONE_KEY, "1")
    logger.info(
        "First-run setup: applied '%s' language preset. "
        "Language settings: language_mode=%s, native_language=%s, "
        "ui_language=%s, chat_language=%s. "
        "To change, use POST /admin/config/preset or POST /admin/config/update.",
        _DEFAULT_PRESET,
        preset["language_mode"],
        preset["native_language"],
        preset["ui_language"],
        preset["chat_language"],
    )


async def get_config() -> dict:
    """
    Return the current admin config with defaults applied for missing keys.
    All numeric values are returned as floats.

    On first run (Redis has no stored config), the English Mode preset is
    automatically applied before returning.
    """
    raw = await redis.get_admin_config_raw()

    # First-run detection: if the setup sentinel is absent, the config store is
    # empty.  Apply the default preset so the bot starts in a known-good state.
    if _SETUP_DONE_KEY not in raw:
        await _first_run_setup()
        raw = await redis.get_admin_config_raw()

    config: dict = dict(_DEFAULTS)
    for k, v in raw.items():
        if k == _SETUP_DONE_KEY:
            continue  # internal sentinel — not a user-facing config field
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


async def apply_preset(preset_name: str) -> dict:
    """
    Apply a named language preset, returning the full config after the update.
    Raises ValueError for unknown preset names.
    """
    preset_name = preset_name.strip().lower()
    if preset_name not in _LANGUAGE_PRESETS:
        available = ", ".join(sorted(_LANGUAGE_PRESETS.keys()))
        raise ValueError(
            f"Unknown preset '{preset_name}'. Available presets: {available}"
        )
    await redis.set_admin_config_bulk(_LANGUAGE_PRESETS[preset_name])
    return await get_config()
