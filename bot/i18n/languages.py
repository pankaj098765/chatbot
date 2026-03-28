"""
bot/i18n/languages.py — Supported language registry.

Defines the canonical list of languages the bot can operate in and
the default values for language-related settings.  Admin config can
restrict ``allowed_languages`` to a subset of this list.

# NEW
"""
from __future__ import annotations

# ISO 639-1 code → display name (in that language where practical)
SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "hi": "हिंदी (Hindi)",
    "es": "Español (Spanish)",
    "fr": "Français (French)",
    "de": "Deutsch (German)",
    "pt": "Português (Portuguese)",
    "ar": "العربية (Arabic)",
    "ru": "Русский (Russian)",
    "tr": "Türkçe (Turkish)",
    "id": "Bahasa Indonesia",
}

# Fallback used when admin has not configured a default language
DEFAULT_LANGUAGE: str = "en"

# Fallback used when admin has not configured a default chat mode
DEFAULT_CHAT_MODE: str = "mixed"

# Valid chat modes
CHAT_MODES: dict[str, str] = {
    "english": "English only",
    "native": "Native language only",
    "mixed": "Mixed (English + native)",
}
