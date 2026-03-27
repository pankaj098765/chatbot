"""
bot/keyboards/inline.py — All inline keyboard factories.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings


def search_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 Search", callback_data="search")
    return builder.as_markup()


def stop_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🛑 Stop", callback_data="stop")
    return builder.as_markup()


def next_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Next", callback_data="next")
    builder.button(text="🛑 Stop", callback_data="stop")
    builder.adjust(2)
    return builder.as_markup()


def payment_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"⭐ Premium — {settings.premium_price_stars} Stars",
        callback_data="buy_premium",
    )
    builder.button(
        text=f"👑 VIP — {settings.vip_price_stars} Stars",
        callback_data="buy_vip",
    )
    builder.adjust(1)
    return builder.as_markup()


def feedback_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👍 Good", callback_data="feedback_good")
    builder.button(text="👎 Bad", callback_data="feedback_bad")
    builder.adjust(2)
    return builder.as_markup()


def gender_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👦 Male", callback_data="gender_male")
    builder.button(text="👧 Female", callback_data="gender_female")
    builder.adjust(2)
    return builder.as_markup()
