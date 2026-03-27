"""
bot/handlers/chat.py — Message relay + gender callback + post-session feedback.
"""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database import mongodb as db
from bot.database import redis_client as redis
from bot.keyboards.inline import search_keyboard
from bot.services import anti_abuse, experience
from bot.services.analytics import track_feedback
from bot.utils.states import UserState

router = Router()


# ─── Message relay ────────────────────────────────────────────────────────────

@router.message(UserState.CONNECTED)
async def relay_message(message: Message, state: FSMContext, bot: Bot) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    text = message.text or ""

    # Abuse check
    bad_score = await anti_abuse.check_and_score_message(user_id, text)
    if bad_score >= 10:
        await message.answer(
            "⚠️ You've been restricted for a short period due to policy violations."
        )
        return

    partner_id = await redis.get_partner(user_id)
    if not partner_id or partner_id < 0:
        # Fallback session — messages are "received" but silently dropped
        # (the BehaviorController loop responds on its own schedule)
        return

    # Relay to real partner
    session_id = await redis.get_session_id(user_id)
    try:
        await bot.send_message(partner_id, text)
        if session_id:
            await redis.increment_message_count(session_id)
            await db.increment_session_messages(session_id)
    except Exception:
        await message.answer(
            "⚠️ Could not deliver your message. Your partner may have disconnected.\n"
            "Use /next to find a new stranger."
        )


# ─── Gender selection callback ────────────────────────────────────────────────

@router.callback_query(F.data.in_({"gender_male", "gender_female"}))
async def cb_gender(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    user_id = callback.from_user.id
    gender = "male" if callback.data == "gender_male" else "female"
    await db.update_user(user_id, {"gender": gender})
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"✅ Gender set to <b>{'Male' if gender == 'male' else 'Female'}</b>.\n\n"
        "Use /search to find a stranger!",
        parse_mode="HTML",
        reply_markup=search_keyboard(),
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

    await callback.message.edit_text(  # type: ignore[union-attr]
        "Thanks for your feedback! 🙏\n\nUse /search to find a new stranger.",
        reply_markup=search_keyboard(),
    )
