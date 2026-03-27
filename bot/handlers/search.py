"""
bot/handlers/search.py — /search, /next, /stop commands and matchmaking loop.

Flow:
  /search → add to queue → poll for match → notify both users → CONNECTED state
  /next   → end current session → immediately re-search
  /stop   → end current session → IDLE state
"""
from __future__ import annotations

import asyncio
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.database import mongodb as db
from bot.database import redis_client as redis
from bot.keyboards.inline import next_keyboard, search_keyboard, stop_keyboard
from bot.services import anti_abuse, experience, fallback, matchmaking, session
from bot.services.analytics import track_match_attempt
from bot.utils.states import UserState

router = Router()

# ─── /search ──────────────────────────────────────────────────────────────────


async def _do_search(message: Message, state: FSMContext, bot: Bot) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]

    # Abuse cooldown check
    if await anti_abuse.is_blocked(user_id):
        await message.answer(
            "⚠️ You've been temporarily restricted due to policy violations. "
            "Please wait a few minutes before searching again."
        )
        return

    user = await db.get_or_create_user(user_id)

    # Consult experience engine to decide action
    action = experience.decide_next_action(user)

    if action == "FALLBACK":
        await state.set_state(UserState.CONNECTED)
        await message.answer(
            "✅ Found a stranger! Say hello 👋",
            reply_markup=next_keyboard(),
        )
        fallback.launch_fallback(bot, user_id)
        return

    # MATCH_REAL or RETRY — add to queue and poll
    await matchmaking.enqueue_user(user_id)
    await state.set_state(UserState.SEARCHING)
    await message.answer("🔍 Searching for a stranger...", reply_markup=stop_keyboard())

    # Poll for a match
    search_start = time.time()
    partner_id: int | None = None
    relaxed_after = 30  # seconds before relaxing filters

    while True:
        elapsed = time.time() - search_start

        # Timeout → trigger fallback
        if elapsed >= settings.max_wait_seconds:
            break

        partner_id = await matchmaking.find_match(user_id)
        if partner_id:
            break

        await asyncio.sleep(settings.queue_poll_interval)

        # Check if user cancelled
        current_state = await state.get_state()
        if current_state != UserState.SEARCHING:
            await matchmaking.dequeue_user(user_id)
            return

    if partner_id:
        # Mutual dequeue
        await matchmaking.dequeue_user(user_id)
        await matchmaking.dequeue_user(partner_id)

        # Create session
        session_id = await session.create_session(bot, user_id, partner_id)

        # Track recent matches to avoid repeat pairings
        await redis.add_recent_match(user_id, partner_id)
        await redis.add_recent_match(partner_id, user_id)

        # Notify both
        wait_time = time.time() - search_start
        await state.set_state(UserState.CONNECTED)

        partner_state_data = {"partner_id": user_id, "session_id": session_id}

        await message.answer(
            "✅ Connected! Say hello to your stranger 👋",
            reply_markup=next_keyboard(),
        )
        try:
            await bot.send_message(
                partner_id,
                "✅ Connected! Say hello to your stranger 👋",
                reply_markup=next_keyboard(),
            )
        except Exception:
            pass

        track_match_attempt(user_id, success=True, wait_time=wait_time)
    else:
        # No match found → trigger fallback
        await matchmaking.dequeue_user(user_id)
        await state.set_state(UserState.CONNECTED)
        await message.answer(
            "✅ Found a stranger! Say hello 👋",
            reply_markup=next_keyboard(),
        )
        fallback.launch_fallback(bot, user_id)
        track_match_attempt(user_id, success=False, wait_time=settings.max_wait_seconds)


@router.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext, bot: Bot) -> None:
    current = await state.get_state()
    if current == UserState.SEARCHING:
        await message.answer("⏳ Already searching! Use /stop to cancel.")
        return
    if current == UserState.CONNECTED:
        await message.answer("💬 You're already in a chat. Use /next or /stop first.")
        return
    await _do_search(message, state, bot)


@router.callback_query(F.data == "search")
async def cb_search(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    current = await state.get_state()
    if current in (UserState.SEARCHING, UserState.CONNECTED):
        return
    await _do_search(callback.message, state, bot)  # type: ignore[arg-type]


# ─── /next ────────────────────────────────────────────────────────────────────


async def _do_next(message: Message, state: FSMContext, bot: Bot) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    partner_id = await redis.get_partner(user_id)

    # End current session
    await session.end_session(user_id, exit_reason="next")

    # Notify partner
    if partner_id and partner_id > 0:
        try:
            await bot.send_message(
                partner_id,
                "Your partner has left the chat. Use /search to find a new stranger.",
                reply_markup=search_keyboard(),
            )
        except Exception:
            pass
        partner_fsm_state = await bot.get_state(partner_id)  # type: ignore[attr-defined]

    # Immediately re-search
    await _do_search(message, state, bot)


@router.message(Command("next"))
async def cmd_next(message: Message, state: FSMContext, bot: Bot) -> None:
    current = await state.get_state()
    if current not in (UserState.CONNECTED, UserState.SEARCHING):
        await message.answer("You're not in a chat. Use /search to start.")
        return
    await _do_next(message, state, bot)


@router.callback_query(F.data == "next")
async def cb_next(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await _do_next(callback.message, state, bot)  # type: ignore[arg-type]


# ─── /stop ────────────────────────────────────────────────────────────────────


async def _do_stop(message: Message, state: FSMContext, bot: Bot) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    partner_id = await redis.get_partner(user_id)

    await session.end_session(user_id, exit_reason="stop")
    await matchmaking.dequeue_user(user_id)
    await state.set_state(UserState.IDLE)

    await message.answer(
        "🛑 Chat ended. Use /search whenever you're ready.",
        reply_markup=search_keyboard(),
    )

    if partner_id and partner_id > 0:
        try:
            await bot.send_message(
                partner_id,
                "Your partner has left. Use /search to find a new stranger.",
                reply_markup=search_keyboard(),
            )
        except Exception:
            pass


@router.message(Command("stop"))
async def cmd_stop(message: Message, state: FSMContext, bot: Bot) -> None:
    current = await state.get_state()
    if current == UserState.IDLE:
        await message.answer("You're not in a chat.")
        return
    await _do_stop(message, state, bot)


@router.callback_query(F.data == "stop")
async def cb_stop(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await _do_stop(callback.message, state, bot)  # type: ignore[arg-type]
