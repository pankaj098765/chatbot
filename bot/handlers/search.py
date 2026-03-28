"""
bot/handlers/search.py — /search, /next, /stop commands and matchmaking loop.

Flow:
  /search → add to queue → poll for match → notify both users → CONNECTED state
  /next   → end current session → immediately re-search (with warm-start boost)
  /stop   → end current session → IDLE state

Fix #6:  Non-premium users see payment psychology hints during search.
Fix #7:  Poll timeout adapts to queue health stats.
Fix #8:  Watchdog re-queues stuck users (runs in retention_engine background task).
Fix #10: /next carries warm-start context to boost next match quality.

# UPDATED: all user-facing strings use t() with the user's ui_language.
          Partner notifications look up the partner's language individually.
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
from bot.i18n import lang_of, t
from bot.keyboards.inline import next_keyboard, search_keyboard, stop_keyboard
from bot.services import anti_abuse, experience, fallback, matchmaking, session
from bot.services.analytics import track_match_attempt
from bot.services.queue_monitor import collect_queue_stats, get_adaptive_poll_timeout
from bot.services.retention_engine import apply_warm_start_boost
from bot.utils.states import UserState

router = Router()


# ─── /search ──────────────────────────────────────────────────────────────────


async def _do_search(
    message: Message,
    state: FSMContext,
    bot: Bot,
    warm_start: bool = False,
) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]

    # Abuse cooldown check
    if await anti_abuse.is_blocked(user_id):
        user = await db.get_user(user_id)
        lang = lang_of(user)
        await message.answer(t("abuse_blocked", lang))
        return

    user = await db.get_or_create_user(user_id)
    lang = lang_of(user)

    # Consult experience engine to decide action
    action = experience.decide_next_action(user)

    if action == "FALLBACK":
        await state.set_state(UserState.CONNECTED)
        await message.answer(
            t("found_stranger", lang),
            reply_markup=next_keyboard(lang),
        )
        fallback.launch_fallback(bot, user_id)
        return

    # MATCH_REAL or RETRY — add to queue and poll
    await matchmaking.enqueue_user(user_id)

    # Fix #10: Apply warm-start boost when triggered by /next
    if warm_start:
        await apply_warm_start_boost(user_id)

    await state.set_state(UserState.SEARCHING)

    # Fix #6: Show payment psychology hint to non-premium users
    search_text = t("search_text", lang)
    if not user.get("is_premium") and not user.get("is_vip"):
        search_text += t("premium_hint", lang)

    await message.answer(
        search_text,
        reply_markup=stop_keyboard(lang),
        parse_mode="HTML",
    )

    # Fix #7: Adapt poll timeout based on queue health
    try:
        queue_stats = await collect_queue_stats()
        max_wait = get_adaptive_poll_timeout(queue_stats, settings.max_wait_seconds)
    except Exception:
        max_wait = settings.max_wait_seconds

    # Poll for a match
    search_start = time.time()
    matched_candidate = None

    while True:
        elapsed = time.time() - search_start

        # Timeout → trigger fallback
        if elapsed >= max_wait:
            break

        matched_candidate = await matchmaking.find_match(user_id)
        if matched_candidate:
            break

        await asyncio.sleep(settings.queue_poll_interval)

        # Check if user cancelled
        current_state = await state.get_state()
        if current_state != UserState.SEARCHING:
            await matchmaking.dequeue_user(user_id)
            return

    if matched_candidate and not matched_candidate.is_simulated:
        partner_id = matched_candidate.user_id

        # Mutual dequeue
        await matchmaking.dequeue_user(user_id)
        await matchmaking.dequeue_user(partner_id)

        # Create session
        session_id = await session.create_session(bot, user_id, partner_id)

        # Track recent matches to avoid repeat pairings
        await redis.add_recent_match(user_id, partner_id)
        await redis.add_recent_match(partner_id, user_id)

        # Notify both — each in their own language
        wait_time = time.time() - search_start
        await state.set_state(UserState.CONNECTED)

        await message.answer(
            t("connected_stranger", lang),
            reply_markup=next_keyboard(lang),
        )
        try:
            partner = await db.get_user(partner_id)
            partner_lang = lang_of(partner)
            await bot.send_message(
                partner_id,
                t("connected_stranger", partner_lang),
                reply_markup=next_keyboard(partner_lang),
            )
        except Exception:
            pass

        track_match_attempt(user_id, success=True, wait_time=wait_time)
    else:
        # No real match found (None or simulated candidate) → trigger fallback
        await matchmaking.dequeue_user(user_id)
        await state.set_state(UserState.CONNECTED)
        await message.answer(
            t("found_stranger", lang),
            reply_markup=next_keyboard(lang),
        )
        fallback.launch_fallback(bot, user_id)
        track_match_attempt(user_id, success=False, wait_time=max_wait)


@router.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext, bot: Bot) -> None:
    current = await state.get_state()
    if current == UserState.SEARCHING:
        user = await db.get_user(message.from_user.id)  # type: ignore[union-attr]
        lang = lang_of(user)
        await message.answer(t("already_searching", lang))
        return
    if current == UserState.CONNECTED:
        user = await db.get_user(message.from_user.id)  # type: ignore[union-attr]
        lang = lang_of(user)
        await message.answer(t("already_in_chat", lang))
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

    # End current session — Feature 4: pass bot for exit experience message
    await session.end_session(user_id, exit_reason="next", bot=bot)

    # Notify partner in their language
    if partner_id and partner_id > 0:
        try:
            partner = await db.get_user(partner_id)
            partner_lang = lang_of(partner)
            await bot.send_message(
                partner_id,
                t("partner_left_next", partner_lang),
                reply_markup=search_keyboard(partner_lang),
            )
        except Exception:
            pass

    # Fix #10: Re-search with warm-start boost
    await _do_search(message, state, bot, warm_start=True)


@router.message(Command("next"))
async def cmd_next(message: Message, state: FSMContext, bot: Bot) -> None:
    current = await state.get_state()
    if current not in (UserState.CONNECTED, UserState.SEARCHING):
        user = await db.get_user(message.from_user.id)  # type: ignore[union-attr]
        lang = lang_of(user)
        await message.answer(t("not_in_chat", lang))
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

    # Feature 4: pass bot for exit experience message
    await session.end_session(user_id, exit_reason="stop", bot=bot)
    await matchmaking.dequeue_user(user_id)
    await state.set_state(UserState.IDLE)

    user = await db.get_user(user_id)
    lang = lang_of(user)
    await message.answer(
        t("chat_ended", lang),
        reply_markup=search_keyboard(lang),
    )

    if partner_id and partner_id > 0:
        try:
            partner = await db.get_user(partner_id)
            partner_lang = lang_of(partner)
            await bot.send_message(
                partner_id,
                t("partner_left_stop", partner_lang),
                reply_markup=search_keyboard(partner_lang),
            )
        except Exception:
            pass


@router.message(Command("stop"))
async def cmd_stop(message: Message, state: FSMContext, bot: Bot) -> None:
    current = await state.get_state()
    if current == UserState.IDLE:
        user = await db.get_user(message.from_user.id)  # type: ignore[union-attr]
        lang = lang_of(user)
        await message.answer(t("not_in_chat_stop", lang))
        return
    await _do_stop(message, state, bot)


@router.callback_query(F.data == "stop")
async def cb_stop(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await _do_stop(callback.message, state, bot)  # type: ignore[arg-type]
