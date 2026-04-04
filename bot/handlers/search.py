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

# UPDATED: language is now admin-controlled globally.
          All user-facing strings use t() with the global UI language from
          get_ui_lang().  All users receive the same language — no per-user lookup.
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
from bot.i18n import get_ui_lang, t
from bot.keyboards.inline import (
    gender_preference_keyboard,
    next_keyboard,
    search_keyboard,
    stop_keyboard,
)
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
    user_id: int | None = None,
) -> None:
    if user_id is None:
        user_id = message.from_user.id  # type: ignore[union-attr]

    # UPDATED: global UI language — same for every user
    lang = await get_ui_lang()

    # Abuse cooldown check
    if await anti_abuse.is_blocked(user_id):
        await message.answer(t("abuse_blocked", lang))
        return

    user = await db.get_or_create_user(user_id)

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

        # UPDATED: all users share the same global language — no per-partner lookup
        wait_time = time.time() - search_start
        await state.set_state(UserState.CONNECTED)

        await message.answer(
            t("connected_stranger", lang),
            reply_markup=next_keyboard(lang),
        )
        try:
            await bot.send_message(
                partner_id,
                t("connected_stranger", lang),
                reply_markup=next_keyboard(lang),
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
    lang = await get_ui_lang()
    if current == UserState.SEARCHING:
        await message.answer(t("already_searching", lang))
        return
    if current == UserState.CONNECTED:
        await message.answer(t("already_in_chat", lang))
        return
    await _do_search(message, state, bot)


@router.callback_query(F.data == "search")
async def cb_search(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    current = await state.get_state()
    if current in (UserState.SEARCHING, UserState.CONNECTED):
        return
    await _do_search(callback.message, state, bot, user_id=callback.from_user.id)  # type: ignore[arg-type]


# ─── /next ────────────────────────────────────────────────────────────────────


async def _do_next(message: Message, state: FSMContext, bot: Bot, user_id: int | None = None) -> None:
    if user_id is None:
        user_id = message.from_user.id  # type: ignore[union-attr]
    partner_id = await redis.get_partner(user_id)
    lang = await get_ui_lang()

    # End current session — Feature 4: pass bot for exit experience message
    await session.end_session(user_id, exit_reason="next", bot=bot)

    # UPDATED: all users share the same global language
    if partner_id and partner_id > 0:
        try:
            await bot.send_message(
                partner_id,
                t("partner_left_next", lang),
                reply_markup=search_keyboard(lang),
            )
        except Exception:
            pass

    # Fix #10: Re-search with warm-start boost
    await _do_search(message, state, bot, warm_start=True, user_id=user_id)


@router.message(Command("next"))
async def cmd_next(message: Message, state: FSMContext, bot: Bot) -> None:
    current = await state.get_state()
    if current not in (UserState.CONNECTED, UserState.SEARCHING):
        lang = await get_ui_lang()
        await message.answer(t("not_in_chat", lang))
        return
    await _do_next(message, state, bot)


@router.callback_query(F.data == "next")
async def cb_next(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await _do_next(callback.message, state, bot, user_id=callback.from_user.id)  # type: ignore[arg-type]


# ─── /stop ────────────────────────────────────────────────────────────────────


async def _do_stop(message: Message, state: FSMContext, bot: Bot, user_id: int | None = None) -> None:
    if user_id is None:
        user_id = message.from_user.id  # type: ignore[union-attr]
    partner_id = await redis.get_partner(user_id)
    lang = await get_ui_lang()

    # Feature 4: pass bot for exit experience message
    await session.end_session(user_id, exit_reason="stop", bot=bot)
    await matchmaking.dequeue_user(user_id)
    await state.set_state(UserState.IDLE)

    await message.answer(
        t("chat_ended", lang),
        reply_markup=search_keyboard(lang),
    )

    # UPDATED: all users share the same global language
    if partner_id and partner_id > 0:
        try:
            await bot.send_message(
                partner_id,
                t("partner_left_stop", lang),
                reply_markup=search_keyboard(lang),
            )
        except Exception:
            pass


@router.message(Command("stop"))
async def cmd_stop(message: Message, state: FSMContext, bot: Bot) -> None:
    current = await state.get_state()
    if current == UserState.IDLE:
        lang = await get_ui_lang()
        await message.answer(t("not_in_chat_stop", lang))
        return
    await _do_stop(message, state, bot)


@router.callback_query(F.data == "stop")
async def cb_stop(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await _do_stop(callback.message, state, bot, user_id=callback.from_user.id)  # type: ignore[arg-type]


# ─── Search by Gender ─────────────────────────────────────────────────────────


@router.callback_query(F.data == "search_by_gender")
async def cb_search_by_gender(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    """Show gender-preference picker to premium/VIP users; locked popup for others."""
    await callback.answer()
    lang = await get_ui_lang()
    current = await state.get_state()
    if current in (UserState.SEARCHING, UserState.CONNECTED):
        return

    user = await db.get_or_create_user(callback.from_user.id)
    if not user.get("is_premium") and not user.get("is_vip"):
        # Non-subscriber: show locked alert popup
        await callback.answer(t("gender_search_locked", lang), show_alert=True)
        return

    # Premium / VIP: ask which gender they want to match with
    await callback.message.answer(  # type: ignore[union-attr]
        t("gender_search_prompt", lang),
        reply_markup=gender_preference_keyboard(lang),
    )


@router.callback_query(F.data.in_({"search_gender_male", "search_gender_female"}))
async def cb_search_gender_pref(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    """Set gender preference and start a gender-filtered search for premium/VIP users."""
    await callback.answer()
    lang = await get_ui_lang()
    current = await state.get_state()
    if current in (UserState.SEARCHING, UserState.CONNECTED):
        return

    user = await db.get_or_create_user(callback.from_user.id)
    if not user.get("is_premium") and not user.get("is_vip"):
        await callback.answer(t("gender_search_locked", lang), show_alert=True)
        return

    pref = "male" if callback.data == "search_gender_male" else "female"
    await db.update_user(callback.from_user.id, {"gender_preference": pref})
    await _do_search(callback.message, state, bot, user_id=callback.from_user.id)  # type: ignore[arg-type]
