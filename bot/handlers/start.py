"""
bot/handlers/start.py — /start and /help commands.

# UPDATED: language is now admin-controlled globally.
  All user-facing strings use t() with the global UI language from
  get_ui_lang(), which reads language_mode + native_language from admin config.
  The /language command and per-user language selection have been REMOVED.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database import mongodb as db
from bot.i18n import get_ui_lang, t
from bot.keyboards.inline import (
    gender_keyboard,
)
from bot.keyboards.menu import main_menu_keyboard
from bot.utils.states import UserState
from config.app_config import app_config

router = Router()


# ─── /start ──────────────────────────────────────────────────────────────────


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    user = message.from_user
    if user is None:
        return

    # Register user on first visit — language is NOT stored per-user
    existing = await db.get_or_create_user(user.id, user.username)

    lang = await get_ui_lang()

    # Ask for gender on first use (used for optional premium filter)
    if existing.get("gender") is None:
        await message.answer(
            t("welcome_message", lang, app_name=app_config.brand_name) + t("gender_prompt", lang),
            parse_mode="HTML",
            reply_markup=gender_keyboard(lang),
        )
    else:
        await message.answer(
            t("welcome_message", lang, app_name=app_config.brand_name),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(lang),
        )

    await state.set_state(UserState.IDLE)


# ─── /help ────────────────────────────────────────────────────────────────────


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    lang = await get_ui_lang()
    await message.answer(t("help_message", lang), parse_mode="HTML")
