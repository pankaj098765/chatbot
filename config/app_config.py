"""
config/app_config.py — Global white-label application configuration.

Loads settings from three sources in increasing priority order:

  1. config/default.json   — shipped defaults (do not edit)
  2. config/config.json    — buyer's custom overrides (edit this)
  3. Environment variables — runtime overrides (.env or deployment env)

Fields
------
brand_name        Name shown in bot welcome messages and admin dashboard.
language_mode     "english" | "native" | "mixed"  — controls how the bot speaks.
                  english → all responses in English
                  native  → all responses in native_language only
                  mixed   → mix of English + native_language (e.g. Hinglish)
native_language   ISO 639-1 code for the native language (e.g. "hi", "es", "fr").
                  Used when language_mode is "native" or "mixed".
                  ADMIN-CONTROLLED ONLY — users cannot override this.
ai_enabled        Enable LLM-powered fallback responses (requires OPENAI_API_KEY).
payment_enabled   Enable Telegram Stars payment commands (/pay, /vip).
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
    # UPDATED: primary language config (admin-only, white-label)
    language_mode: str          # "english" | "native" | "mixed"
    native_language: str        # ISO 639-1 code, e.g. "hi", "es", "fr"
    ai_enabled: bool
    payment_enabled: bool

    @property
    def ui_language(self) -> str:
        """Derive the UI display language from language_mode + native_language."""
        if self.language_mode == "english":
            return "en"
        return self.native_language


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

    # UPDATED: language_mode and native_language replace old default_language /
    # allowed_languages / default_chat_mode.  Env vars take priority, then
    # config.json / default.json, then safe fallbacks.
    language_mode = (
        os.getenv("LANGUAGE_MODE")
        or str(merged.get("language_mode", "english"))
    )
    if language_mode not in ("english", "native", "mixed"):
        language_mode = "english"

    native_language = (
        os.getenv("NATIVE_LANGUAGE")
        or str(merged.get("native_language", "en"))
    ).strip().lower()
    if not native_language:
        native_language = "en"

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
        language_mode=language_mode,
        native_language=native_language,
        ai_enabled=ai_enabled,
        payment_enabled=payment_enabled,
    )


app_config = _get_app_config()
