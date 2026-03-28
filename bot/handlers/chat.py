"""
bot/handlers/chat.py — Message relay + gender callback + post-session feedback.

Fix #1:  Feedback handler now calls experience.update_feedback_score to update
         the user's positive/negative feedback counters for priority scoring.
Fix #9:  Incoming messages are scanned for gender-check intent ("m", "m?", etc.)
         Users showing this intent get their priority reduced and are flagged
         so they preferentially match with others doing the same.

# UPDATED
Feature 1: Each relayed message records a per-user timestamp in Redis so
           session.compute_engagement_score can calculate reply_ratio and
           response_delay_variance when the session ends.
Feature 4: Post-session exit experience messages are triggered via
           session.end_session(bot=bot) in the search handlers.
Multilingual: all user-facing strings use t() with the user's ui_language.
"""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database import mongodb as db
from bot.database import redis_client as redis
from bot.i18n import lang_of, t
from bot.keyboards.inline import feedback_keyboard, search_keyboard
from bot.services import anti_abuse, experience
from bot.services.analytics import track_feedback
from bot.services.matchmaking import calc_priority_score
from bot.utils.states import UserState

router = Router()

# Fix #9: Patterns that indicate the user is doing a gender check
_GENDER_CHECK_PATTERNS = frozenset({
    "m", "m?", "male?", "f", "f?", "female?",
    "boy?", "girl?", "guy?", "asl", "asl?",
    "male", "female",
})


# ─── Message relay ────────────────────────────────────────────────────────────

@router.message(UserState.CONNECTED)
async def relay_message(message: Message, state: FSMContext, bot: Bot) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    text = message.text or ""

    user = await db.get_user(user_id)
    lang = lang_of(user)

    # Abuse check
    bad_score = await anti_abuse.check_and_score_message(user_id, text)
    if bad_score >= 10:
        await message.answer(t("abuse_restricted", lang))
        return

    # Fix #9: Intent detection — detect gender-check messages
    normalized = text.strip().lower()
    if normalized in _GENDER_CHECK_PATTERNS:
        await db.update_user(user_id, {"intent": "gender_check"})
        # Slightly deprioritise this user so gender-check users cluster together
        if user:
            new_score = calc_priority_score(user) - 15
            await redis.add_to_queue(user_id, new_score)

    partner_id = await redis.get_partner(user_id)
    if not partner_id or partner_id < 0:
        # Fallback session — store the user's message so the LLM engine can use
        # it as context when generating the next response, then return.
        if text:
            await redis.set_fallback_user_message(user_id, text)
        return

    # Relay to real partner
    session_id = await redis.get_session_id(user_id)
    try:
        await bot.send_message(partner_id, text)
        if session_id:
            await redis.increment_message_count(session_id)
            await db.increment_session_messages(session_id)
            # Feature 1: Record per-user message timestamp for engagement scoring
            await redis.record_user_message_time(session_id, user_id)
    except Exception:
        await message.answer(t("delivery_failed", lang))


# ─── Gender selection callback ────────────────────────────────────────────────

@router.callback_query(F.data.in_({"gender_male", "gender_female"}))
async def cb_gender(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    user_id = callback.from_user.id
    gender = "male" if callback.data == "gender_male" else "female"
    await db.update_user(user_id, {"gender": gender})

    user = await db.get_user(user_id)
    lang = lang_of(user)
    key = "gender_set_male" if gender == "male" else "gender_set_female"

    await callback.message.edit_text(  # type: ignore[union-attr]
        t(key, lang),
        parse_mode="HTML",
        reply_markup=search_keyboard(lang),
    )
    await state.set_state(UserState.IDLE)


# ─── Post-session feedback ────────────────────────────────────────────────────

@router.callback_query(F.data.in_({"feedback_good", "feedback_bad"}))
async def cb_feedback(callback: CallbackQuery) -> None:
    await callback.answer()
    user_id = callback.from_user.id
    rating = "good" if callback.data == "feedback_good" else "bad"
    track_feedback(user_id, rating)

    # Record outcome in experience engine
    outcome = "GOOD_CHAT" if rating == "good" else "BAD_CHAT"
    await experience.record_outcome(user_id, outcome)

    # Fix #1: Update feedback counters for priority scoring
    await experience.update_feedback_score(user_id, positive=(rating == "good"))

    user = await db.get_user(user_id)
    lang = lang_of(user)

    await callback.message.edit_text(  # type: ignore[union-attr]
        t("feedback_thanks", lang),
        reply_markup=search_keyboard(lang),
    )
