"""
bot/keyboards/inline.py — All inline keyboard factories.

# UPDATED: all keyboard factories now accept an optional lang parameter so
button labels are rendered in the user's chosen language via t().
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings
from bot.i18n import t
from bot.i18n.languages import SUPPORTED_LANGUAGES


def search_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("search_button", lang), callback_data="search")
    return builder.as_markup()


def stop_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("stop_button", lang), callback_data="stop")
    return builder.as_markup()


def next_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("next_button", lang), callback_data="next")
    builder.button(text=t("stop_button", lang), callback_data="stop")
    builder.adjust(2)
    return builder.as_markup()


def payment_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("premium_button", lang, price=settings.premium_price_stars),
        callback_data="buy_premium",
    )
    builder.button(
        text=t("vip_button", lang, price=settings.vip_price_stars),
        callback_data="buy_vip",
    )
    builder.adjust(1)
    return builder.as_markup()


def feedback_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("feedback_good_button", lang), callback_data="feedback_good")
    builder.button(text=t("feedback_bad_button", lang), callback_data="feedback_bad")
    builder.adjust(2)
    return builder.as_markup()


def gender_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("gender_male_button", lang), callback_data="gender_male")
    builder.button(text=t("gender_female_button", lang), callback_data="gender_female")
    builder.adjust(2)
    return builder.as_markup()


def language_keyboard(
    allowed: list[str] | None = None,
    lang: str = "en",
) -> InlineKeyboardMarkup:
    """# NEW
    Show all (or a filtered subset of) supported languages as selectable buttons.

    Parameters
    ----------
    allowed:
        List of ISO codes to display.  If None, all SUPPORTED_LANGUAGES are shown.
    lang:
        Current UI language (used only if we ever add a cancel/back button).
    """
    builder = InlineKeyboardBuilder()
    codes = allowed if allowed is not None else list(SUPPORTED_LANGUAGES.keys())
    for code in codes:
        display = SUPPORTED_LANGUAGES.get(code, code.upper())
        builder.button(text=display, callback_data=f"lang_select_{code}")
    builder.adjust(2)
    return builder.as_markup()


def language_filter_keyboard(matches: list[str]) -> InlineKeyboardMarkup:
    """# NEW
    Show a filtered subset of languages based on the user's search query.

    Parameters
    ----------
    matches:
        List of ISO codes whose display names matched the user's query.
    """
    builder = InlineKeyboardBuilder()
    for code in matches:
        display = SUPPORTED_LANGUAGES.get(code, code.upper())
        builder.button(text=display, callback_data=f"lang_select_{code}")
    builder.adjust(2)
    return builder.as_markup()
