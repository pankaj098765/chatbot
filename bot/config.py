"""
bot/config.py — Central configuration loaded from environment variables.

Priority (highest to lowest):
  1. Environment variables  — set by the shell / Docker / cloud platform
  2. .env file              — loaded only as a fallback (override=False)
  3. Default values         — hard-coded sensible defaults per field

The .env file is *optional*: if it is absent no error is raised.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load .env only as a fallback — existing env vars are NEVER overwritten.
# dotenv returns False silently when the file is missing, so this is safe.
load_dotenv(override=False)

logger = logging.getLogger(__name__)


def get_env(key: str, default: str = "", required: bool = False) -> str:
    """Return the value of *key* from the environment (or *default*).

    Raises ``ValueError`` when *required* is ``True`` and no value is found.
    Always returns a ``str``; pass ``default=""`` to get an empty string
    when the key is absent.
    """
    value = os.getenv(key) or default
    if required and not value:
        raise ValueError(f"Missing required environment variable: {key}")
    return value


@dataclass(frozen=True)
class Settings:
    bot_token: str
    mongodb_uri: str
    redis_url: str
    db_name: str
    debug: bool

    # Anti-abuse thresholds
    bad_score_threshold: int = 10
    spam_window_seconds: int = 60
    spam_message_limit: int = 10

    # Matchmaking
    queue_poll_interval: float = 1.0   # seconds between queue polls
    max_wait_seconds: int = 120        # max time in queue before fallback

    # Payment — Telegram Stars (XTR)
    premium_price_stars: int = 100
    vip_price_stars: int = 250
    subscription_days: int = 30

    # LLM integration
    openai_api_key: str = ""      # legacy — still supported for OpenAI
    llm_model: str = ""           # optional — each provider has a built-in default
    llm_enabled: bool = True      # global kill-switch

    # Multi-provider LLM config
    # llm_provider: "openai" | "gemini" | "grok" | "groq" | "mistral" |
    #               "deepseek" | "anthropic" | "together" | "custom"
    llm_provider: str = "openai"
    # llm_api_key: generic key for the selected provider.
    # Falls back to openai_api_key when provider == "openai" and this is empty.
    llm_api_key: str = ""
    # llm_base_url: override the REST endpoint (required for "custom",
    # auto-populated for all built-in providers).
    llm_base_url: str = ""


def _get_settings() -> Settings:
    token = get_env("BOT_TOKEN", required=True)
    return Settings(
        bot_token=token,
        mongodb_uri=get_env("MONGODB_URI", "mongodb://localhost:27017"),
        redis_url=get_env("REDIS_URL", "redis://localhost:6379"),
        db_name=get_env("DB_NAME", "anonymous_chat"),
        debug=get_env("DEBUG", "false").lower() == "true",
        openai_api_key=get_env("OPENAI_API_KEY", ""),
        llm_model=get_env("LLM_MODEL", "").strip(),
        llm_enabled=get_env("LLM_ENABLED", "true").lower() == "true",
        llm_provider=get_env("LLM_PROVIDER", "openai").strip().lower(),
        llm_api_key=get_env("LLM_API_KEY", ""),
        llm_base_url=get_env("LLM_BASE_URL", ""),
    )


settings = _get_settings()


def log_config_summary() -> None:
    """Log which configuration keys are set, without revealing their values."""
    # Build the display list without keeping sensitive values near log calls.
    lines: list[str] = [
        f"BOT_TOKEN: {'SET' if settings.bot_token else 'NOT SET'}",
        f"MONGODB_URI: {'SET' if settings.mongodb_uri else 'NOT SET'}",
        f"REDIS_URL: {'SET' if settings.redis_url else 'NOT SET'}",
        f"DB_NAME: {'SET' if settings.db_name else 'NOT SET'}",
        f"LLM_PROVIDER: {'SET' if settings.llm_provider else 'NOT SET'}",
        f"LLM_API_KEY: {'SET' if settings.llm_api_key else 'NOT SET'}",
        f"OPENAI_API_KEY: {'SET' if settings.openai_api_key else 'NOT SET'}",
        f"LLM_ENABLED: {'true' if settings.llm_enabled else 'false'}",
        f"DEBUG: {'true' if settings.debug else 'false'}",
    ]
    logger.debug("Config loaded:")
    for line in lines:
        logger.debug("  - %s", line)
