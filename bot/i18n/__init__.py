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

        t("welcome_message", "hi")
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


def lang_of(user: dict | None) -> str:
    """# NEW
    Extract the ``ui_language`` from a user document, defaulting to ``"en"``.

    Usage::

        user = await db.get_user(user_id)
        lang = lang_of(user)
        await message.answer(t("welcome_message", lang))
    """
    if not user:
        return "en"
    return user.get("ui_language") or "en"
