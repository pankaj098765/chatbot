"""
bot/config.py — Central configuration loaded from environment variables.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


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
    llm_model: str = "gpt-4o-mini"
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
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN environment variable is not set")
    return Settings(
        bot_token=token,
        mongodb_uri=os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        db_name=os.getenv("DB_NAME", "anonymous_chat"),
        debug=os.getenv("DEBUG", "false").lower() == "true",
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        llm_enabled=os.getenv("LLM_ENABLED", "true").lower() == "true",
        llm_provider=os.getenv("LLM_PROVIDER", "openai").strip().lower(),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
    )


settings = _get_settings()
