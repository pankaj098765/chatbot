"""
admin/config.py — Configuration for the admin dashboard service.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class AdminSettings:
    redis_url: str
    mongodb_uri: str
    db_name: str
    admin_token: str


def _get_settings() -> AdminSettings:
    token = os.getenv("ADMIN_TOKEN")
    if not token:
        raise ValueError(
            "ADMIN_TOKEN environment variable is required but not set. "
            "Please configure it in your .env file."
        )
    return AdminSettings(
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        mongodb_uri=os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
        db_name=os.getenv("DB_NAME", "anonymous_chat"),
        admin_token=token,
    )


settings = _get_settings()
