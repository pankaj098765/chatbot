from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from bot.i18n import t


def main_menu_keyboard(lang: str = "en") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("search_button", lang)),
                KeyboardButton(text=t("search_by_gender_button", lang)),
            ]
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
