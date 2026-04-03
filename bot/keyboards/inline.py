"""
bot/keyboards/inline.py — All inline keyboard factories.

# UPDATED: language is now admin-controlled globally.
  All keyboard factories accept an optional lang parameter so button labels
  are rendered in the global UI language via t().
  language_keyboard and language_filter_keyboard have been REMOVED —
  users no longer select their own language.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings
from bot.i18n import t


def search_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("search_button", lang), callback_data="search")
    builder.button(text=t("search_by_gender_button", lang), callback_data="search_by_gender")
    builder.adjust(1)
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


def gender_preference_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Gender preference picker shown to premium/VIP users before a gender-filtered search."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("match_with_male_button", lang), callback_data="search_gender_male")
    builder.button(text=t("match_with_female_button", lang), callback_data="search_gender_female")
    builder.adjust(2)
    return builder.as_markup()

# REMOVED: language_keyboard() — language is admin-controlled globally
# REMOVED: language_filter_keyboard() — users no longer select their own language
