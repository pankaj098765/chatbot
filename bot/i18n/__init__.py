"""
bot/i18n/__init__.py — Internationalization (i18n) helper.

Provides the t() translation function that loads language strings from
JSON files in this directory and falls back to English when a key is
missing.  All lookups are cached in-process so JSON files are parsed
only once per language per process lifetime.

# NEW
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_I18N_DIR = Path(__file__).parent

# In-process cache: lang → {key: translated_string}
_TRANSLATIONS: dict[str, dict[str, str]] = {}


def _load_lang(lang: str) -> dict[str, str]:
    """Load and return the translation dict for *lang*.

    Returns an empty dict if the file is missing or contains invalid JSON,
    so callers always receive a dict they can safely query.
    """
    path = _I18N_DIR / f"{lang}.json"
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        logger.warning("i18n: no translation file for lang=%r", lang)
        return {}
    except json.JSONDecodeError as exc:
        logger.error("i18n: invalid JSON for lang=%r: %s", lang, exc)
        return {}


def _get(lang: str) -> dict[str, str]:
    """Return cached translation dict for *lang*, loading it on first access."""
    if lang not in _TRANSLATIONS:
        _TRANSLATIONS[lang] = _load_lang(lang)
    return _TRANSLATIONS[lang]


def t(key: str, lang: str = "en", **kwargs: object) -> str:
    """# NEW
    Return the translated string for *key* in *lang*.

    Resolution order:
      1. Look up *key* in the *lang* translation file.
      2. If not found (and *lang* != "en"), fall back to English.
      3. If still not found, return *key* itself so the UI never breaks.

    Optional keyword arguments are interpolated with ``str.format_map()``.

    Examples::

        t("welcome_message", lang, app_name=app_config.brand_name)
        t("premium_button", lang, price=100)
        t("vip_info", lang, vip_price=250, subscription_days=30)
    """
    text = _get(lang).get(key)
    if text is None and lang != "en":
        text = _get("en").get(key)
    if text is None:
        logger.debug("i18n: missing key=%r for lang=%r", key, lang)
        text = key
    if kwargs:
        try:
            text = text.format_map(kwargs)
        except (KeyError, ValueError):
            pass
    return text


async def get_ui_lang() -> str:
    """# UPDATED
    Return the UI language for buttons/menus from admin configuration.

    Prefers the explicit ``ui_language`` config key (set independently of
    chat language).  Falls back to the derived value from language_mode +
    native_language for backward compatibility.

    Falls back to "en" on any error so the bot always has a safe default.
    """
    try:
        from bot.services import admin_control  # lazy import — avoids circular deps
        from bot.i18n.languages import SUPPORTED_LANGUAGES
        config = await admin_control.get_config()

        # Prefer explicitly set ui_language
        ui_language = str(config.get("ui_language", "")).strip().lower()
        if ui_language and ui_language in SUPPORTED_LANGUAGES:
            return ui_language

        # Backward compat: derive from language_mode + native_language
        language_mode = str(config.get("language_mode", "english"))
        native_language = str(config.get("native_language", "en"))
        if language_mode == "english":
            return "en"
        if native_language not in SUPPORTED_LANGUAGES:
            logger.warning(
                "get_ui_lang: unsupported native_language=%r, falling back to 'en'",
                native_language,
            )
            return "en"
        return native_language
    except Exception:
        return "en"


async def get_chat_lang() -> str:
    """
    Return the AI/LLM chat language from admin configuration.

    Reads the explicit ``chat_language`` config key.  Falls back to
    ``native_language``, then to "en" for safety.
    """
    try:
        from bot.services import admin_control  # lazy import — avoids circular deps
        from bot.i18n.languages import SUPPORTED_LANGUAGES
        config = await admin_control.get_config()

        chat_language = str(config.get("chat_language", "")).strip().lower()
        if chat_language and chat_language in SUPPORTED_LANGUAGES:
            return chat_language

        # Fallback: native_language
        native_language = str(config.get("native_language", "en"))
        if native_language in SUPPORTED_LANGUAGES:
            return native_language
        return "en"
    except Exception:
        return "en"


def lang_of(user: dict | None) -> str:
    """# DEPRECATED — use ``await get_ui_lang()`` instead.

    Previously extracted ui_language from a user document.  Language is now
    admin-controlled globally; this function is kept only for any call sites
    not yet migrated and always returns the safe English fallback.
    """
    return "en"
