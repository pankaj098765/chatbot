"""
bot/handlers/start.py — /start and /help commands.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.database import mongodb as db
from bot.keyboards.inline import search_keyboard, gender_keyboard
from bot.utils.states import UserState
from aiogram.fsm.context import FSMContext

router = Router()

_WELCOME = (
    "👋 Welcome to <b>Anonymous Chat</b>!\n\n"
    "You'll be matched with a random stranger for a private, anonymous conversation.\n\n"
    "• 🔍 /search — find a stranger\n"
    "• ⏭ /next   — skip to next partner\n"
    "• 🛑 /stop   — end current chat\n"
    "• 💳 /pay    — Premium & VIP plans\n\n"
    "<i>Your identity is never revealed.</i>"
)

_HELP = (
    "<b>Commands:</b>\n"
    "/start  — show welcome screen\n"
    "/search — join the queue and find a match\n"
    "/next   — disconnect and find the next stranger\n"
    "/stop   — leave the current chat\n"
    "/pay    — view Premium / VIP plans\n"
    "/vip    — learn about VIP benefits\n\n"
    "<b>Premium</b> (⭐100 Stars): gender filter\n"
    "<b>VIP</b> (⭐250 Stars): priority matching"
)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    user = message.from_user
    if user is None:
        return

    # Register user if first visit
    await db.get_or_create_user(user.id, user.username)

    # Ask for gender on first use (used for optional premium filter)
    existing = await db.get_user(user.id)
    if existing and existing.get("gender") is None:
        await message.answer(
            _WELCOME + "\n\nFirst, tell us your gender (used for Premium matching):",
            parse_mode="HTML",
            reply_markup=gender_keyboard(),
        )
    else:
        await message.answer(_WELCOME, parse_mode="HTML", reply_markup=search_keyboard())

    await state.set_state(UserState.IDLE)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(_HELP, parse_mode="HTML")
