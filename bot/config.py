"""
bot/config.py — Central configuration loaded from environment variables.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

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
    )


settings = _get_settings()
