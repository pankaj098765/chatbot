"""
config/app_config.py — Global white-label application configuration.

Loads settings from three sources in increasing priority order:

  1. config/default.json   — shipped defaults (do not edit)
  2. config/config.json    — buyer's custom overrides (edit this)
  3. Environment variables — runtime overrides (.env or deployment env)

Fields
------
brand_name          Name shown in bot welcome messages and admin dashboard.
default_language    ISO 639-1 code for new users' default UI language.
allowed_languages   List of ISO codes available in the /language selector.
default_chat_mode   "english" | "native" | "mixed"
ai_enabled          Enable LLM-powered fallback responses (requires OPENAI_API_KEY).
payment_enabled     Enable Telegram Stars payment commands (/pay, /vip).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_CONFIG_DIR = Path(__file__).parent


@dataclass(frozen=True)
class AppConfig:
    brand_name: str
    default_language: str
    allowed_languages: list
    default_chat_mode: str
    ai_enabled: bool
    payment_enabled: bool


def _load_json(path: Path) -> dict:
    """Load a JSON file, returning an empty dict on any error."""
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def _parse_bool(value: str) -> bool:
    """Parse a boolean from a string environment variable."""
    return value.strip().lower() in ("true", "1", "yes", "on")


def _get_app_config() -> AppConfig:
    # 1. Start with defaults from default.json
    merged: dict = _load_json(_CONFIG_DIR / "default.json")

    # 2. Overlay buyer's config.json (higher priority)
    merged.update(_load_json(_CONFIG_DIR / "config.json"))

    # 3. Apply environment variable overrides (highest priority)

    brand_name = os.getenv("BRAND_NAME") or str(merged.get("brand_name", "Anonymous Chat"))

    default_language = os.getenv("DEFAULT_LANGUAGE") or str(
        merged.get("default_language", "en")
    )

    env_langs = os.getenv("ALLOWED_LANGUAGES")
    if env_langs:
        allowed_languages = [c.strip() for c in env_langs.split(",") if c.strip()]
    elif isinstance(merged.get("allowed_languages"), list):
        allowed_languages = [str(c) for c in merged["allowed_languages"]]
    elif isinstance(merged.get("allowed_languages"), str):
        allowed_languages = [
            c.strip() for c in merged["allowed_languages"].split(",") if c.strip()
        ]
    else:
        allowed_languages = ["en", "hi", "es"]

    default_chat_mode = os.getenv("DEFAULT_CHAT_MODE") or str(
        merged.get("default_chat_mode", "mixed")
    )

    env_ai = os.getenv("AI_ENABLED")
    ai_enabled = _parse_bool(env_ai) if env_ai is not None else bool(
        merged.get("ai_enabled", True)
    )

    env_payment = os.getenv("PAYMENT_ENABLED")
    payment_enabled = _parse_bool(env_payment) if env_payment is not None else bool(
        merged.get("payment_enabled", True)
    )

    return AppConfig(
        brand_name=brand_name,
        default_language=default_language,
        allowed_languages=allowed_languages,
        default_chat_mode=default_chat_mode,
        ai_enabled=ai_enabled,
        payment_enabled=payment_enabled,
    )


app_config = _get_app_config()
