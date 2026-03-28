"""
bot/handlers/start.py — /start, /help and /language commands.

# UPDATED: all user-facing strings are rendered via t() using the user's
ui_language.  The /language command starts a searchable language-selection
flow using FSM state SELECTING_LANGUAGE.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database import mongodb as db
from bot.i18n import lang_of, t
from bot.i18n.languages import CHAT_MODES, SUPPORTED_LANGUAGES
from bot.keyboards.inline import (
    gender_keyboard,
    language_filter_keyboard,
    language_keyboard,
    search_keyboard,
)
from bot.services import admin_control
from bot.utils.states import UserState
from config.app_config import app_config

router = Router()


# ─── /start ──────────────────────────────────────────────────────────────────


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    user = message.from_user
    if user is None:
        return

    # Register user if first visit; pick up admin default language for new users
    existing = await db.get_user(user.id)
    if existing is None:
        config = await admin_control.get_config()
        default_lang = str(config.get("default_language", "en"))
        default_mode = str(config.get("default_chat_mode", "mixed"))
        existing = await db.get_or_create_user(user.id, user.username)
        await db.update_user(
            user.id,
            {
                "ui_language": default_lang,
                "chat_language": default_lang,
                "chat_mode": default_mode,
            },
        )
        existing = await db.get_user(user.id) or existing

    lang = lang_of(existing)

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
            reply_markup=search_keyboard(lang),
        )

    await state.set_state(UserState.IDLE)


# ─── /help ────────────────────────────────────────────────────────────────────


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    user = await db.get_user(user_id)
    lang = lang_of(user)
    await message.answer(t("help_message", lang), parse_mode="HTML")


# ─── /language — searchable language selector ────────────────────────────────


@router.message(Command("language"))
async def cmd_language(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    user = await db.get_user(user_id)
    lang = lang_of(user)

    # Determine which languages the admin has enabled
    config = await admin_control.get_config()
    allowed_raw = str(config.get("allowed_languages", "en,hi,es"))
    allowed = [c.strip() for c in allowed_raw.split(",") if c.strip()]

    await message.answer(
        t("language_select_prompt", lang),
        parse_mode="HTML",
        reply_markup=language_keyboard(allowed=allowed, lang=lang),
    )
    await state.set_state(UserState.SELECTING_LANGUAGE)


@router.message(UserState.SELECTING_LANGUAGE)
async def language_filter_input(message: Message, state: FSMContext) -> None:
    """# NEW
    Filter the language list as the user types.  Matches on both ISO code and
    display name (case-insensitive), then shows matching buttons.
    """
    user_id = message.from_user.id  # type: ignore[union-attr]
    user = await db.get_user(user_id)
    lang = lang_of(user)
    query = (message.text or "").strip().lower()

    config = await admin_control.get_config()
    allowed_raw = str(config.get("allowed_languages", "en,hi,es"))
    allowed = [c.strip() for c in allowed_raw.split(",") if c.strip()]

    matches = [
        code
        for code in allowed
        if query in code.lower() or query in SUPPORTED_LANGUAGES.get(code, "").lower()
    ]

    if not matches:
        await message.answer(
            t("language_filter_empty", lang, query=message.text or ""),
            parse_mode="HTML",
        )
        return

    await message.answer(
        t("language_filter_results", lang),
        parse_mode="HTML",
        reply_markup=language_filter_keyboard(matches),
    )


@router.callback_query(F.data.startswith("lang_select_"))
async def cb_language_select(callback: CallbackQuery, state: FSMContext) -> None:
    """# NEW
    Handle language selection from the inline keyboard.
    Updates both ui_language and chat_language; preserves existing chat_mode.
    """
    await callback.answer()
    user_id = callback.from_user.id
    code = callback.data.replace("lang_select_", "")  # type: ignore[union-attr]

    # Validate the code is in our supported list
    if code not in SUPPORTED_LANGUAGES:
        return

    user = await db.get_user(user_id)
    chat_mode = (user.get("chat_mode") if user else None) or "mixed"

    await db.update_user(
        user_id,
        {
            "ui_language": code,
            "chat_language": code,
        },
    )

    language_name = SUPPORTED_LANGUAGES[code]
    chat_mode_display = CHAT_MODES.get(chat_mode, chat_mode)

    await callback.message.edit_text(  # type: ignore[union-attr]
        t("language_set", code, language_name=language_name, chat_mode=chat_mode_display),
        parse_mode="HTML",
        reply_markup=search_keyboard(code),
    )
    await state.set_state(UserState.IDLE)
