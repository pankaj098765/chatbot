"""
bot/services/session.py — Session lifecycle management.

Manages:
  - Creating sessions (Redis hot-state + MongoDB persistence)
  - Relaying messages between partners
  - Ending sessions with outcome tracking

Fix #3:  Session durations are passed to experience.record_outcome for churn detection.
Fix #10: Warm start context (session_type + outcome) is saved to Redis on session end.

# UPDATED
Feature 1: Engagement-based match quality — compute engagement_score from
           message count, reply ratio, and response-delay variance; store per session.
Feature 4: Session exit experience — send a quality-aware farewell message to the
           user after every session ends.
"""
from __future__ import annotations

import statistics
import time
from typing import Optional

from aiogram import Bot

from bot.database import mongodb as db
from bot.database import redis_client as redis
from bot.i18n import get_ui_lang, t
from bot.utils.helpers import generate_session_id

_FALLBACK_PARTNER_ID = -1

# Feature 1: Minimum engagement_score to classify a session as GOOD
_ENGAGEMENT_GOOD_THRESHOLD = 3.0
# Below this score the session is classified as BAD
_ENGAGEMENT_BAD_THRESHOLD = 1.0


async def create_session(
    bot: Bot,
    user1_id: int,
    user2_id: int,
    tone: str = "neutral",
) -> str:
    """Create a new session between two users. Returns session_id."""
    session_id = generate_session_id()
    # Store hot-state in Redis (including tone for session consistency)
    await redis.set_session(user1_id, user2_id, session_id)
    await redis.set_session_tone(user1_id, tone)
    await redis.set_session_tone(user2_id, tone)
    # Persist to MongoDB
    await db.create_session(session_id, user1_id, user2_id, tone=tone)
    return session_id


async def get_partner(user_id: int) -> Optional[int]:
    return await redis.get_partner(user_id)


async def relay_message(bot: Bot, from_user_id: int, text: str) -> bool:
    """
    Relay a text message from from_user_id to their partner.
    Returns True if relayed, False if no partner found.
    """
    partner_id = await redis.get_partner(from_user_id)
    if not partner_id:
        return False
    session_id = await redis.get_session_id(from_user_id)
    try:
        await bot.send_message(partner_id, text)
        if session_id:
            await redis.increment_message_count(session_id)
            await db.increment_session_messages(session_id)
    except Exception:
        pass
    return True


# ─── Feature 1: Engagement scoring helpers ───────────────────────────────────

async def compute_engagement_score(
    session_id: str,
    user1_id: int,
    user2_id: int,
) -> float:
    """
    # NEW
    Compute an engagement score for a session.

    engagement_score = message_count + reply_ratio + response_delay_variance_score

    - message_count: raw total messages exchanged
    - reply_ratio:   balance of participation (0 = one-sided, 1 = perfectly equal)
    - variance_score: normalised variance in response timing (more variance = more natural)
    """
    msg_count = await redis.get_message_count(session_id)

    times1 = await redis.get_user_message_times(session_id, user1_id)
    times2 = await redis.get_user_message_times(session_id, user2_id)

    n1, n2 = len(times1), len(times2)
    max_n = max(n1, n2)

    # Reply ratio — how balanced the conversation is
    reply_ratio = (min(n1, n2) / max_n) if max_n > 0 else 0.0

    # Response-delay variance — combined timing of both sides
    variance_score = 0.0
    all_times = sorted(times1 + times2)
    if len(all_times) >= 3:
        delays = [all_times[i + 1] - all_times[i] for i in range(len(all_times) - 1)]
        if len(delays) > 1:
            var = statistics.variance(delays)
            # Normalise: variance up to ~100 s² is considered rich/natural
            variance_score = min(var / 100.0, 1.0)

    return float(msg_count) + reply_ratio + variance_score


# ─── Feature 4: Session exit experience ──────────────────────────────────────

def get_exit_experience_message(quality: str | None, lang: str = "en") -> str:
    """
    # NEW
    Return a short post-session message that matches the session quality.
    """
    if quality == "GOOD_CHAT":
        return t("exit_good_chat", lang)
    if quality == "BAD_CHAT":
        return t("exit_bad_chat", lang)
    return t("exit_neutral", lang)


async def send_exit_experience(bot: Bot, user_id: int, quality: str | None, lang: str = "en") -> None:
    """
    # NEW
    Send the post-session experience message to user_id.
    Silently swallowed on delivery failure (user may have blocked the bot).
    """
    try:
        await bot.send_message(user_id, get_exit_experience_message(quality, lang))
    except Exception:
        pass


async def end_session(
    user_id: int,
    exit_reason: str = "user_stop",
    quality: str | None = None,
    bot: Bot | None = None,
) -> Optional[str]:
    """
    End the session for user_id (and their partner).
    Returns the session_id if a session existed, else None.

    Also records session duration for churn detection (Fix #3) and
    persists warm-start context for the next /next call (Fix #10).

    # UPDATED
    Feature 1: Computes engagement_score from per-user message timestamps and
               stores it on the session document. Uses it to determine quality
               when quality is not explicitly provided.
    Feature 4: If bot is supplied, sends a quality-aware exit experience message
               to user_id after the session closes.
    """
    session_id = await redis.get_session_id(user_id)
    if not session_id:
        return None

    msg_count = await redis.get_message_count(session_id)
    elapsed = await redis.get_search_elapsed(user_id)

    # Resolve partner and both user IDs for engagement scoring
    partner_id = await redis.get_partner(user_id)
    session_doc = await db.get_session(session_id)
    if session_doc:
        user1_id = session_doc.get("user1_id", user_id)
        user2_id = session_doc.get("user2_id", partner_id or user_id)
    else:
        user1_id, user2_id = user_id, (partner_id or user_id)

    # Feature 1: Compute engagement_score
    engagement_score = await compute_engagement_score(session_id, user1_id, user2_id)

    # Determine quality from engagement_score if not provided
    if quality is None:
        if engagement_score >= _ENGAGEMENT_GOOD_THRESHOLD:
            quality = "GOOD_CHAT"
        elif engagement_score < _ENGAGEMENT_BAD_THRESHOLD or msg_count == 0:
            quality = "BAD_CHAT"
        # else: quality stays None (neutral / unknown)

    await db.end_session(
        session_id=session_id,
        exit_reason=exit_reason,
        message_count=msg_count,
        duration=elapsed,
        quality=quality,
    )
    # Feature 1: Persist engagement_score on the session document
    await db.update_session(session_id, {"engagement_score": engagement_score})

    # Clean up hot state
    await redis.clear_session(user_id)
    await redis.clear_message_count(session_id)

    # Clean up per-user message timestamp data
    await redis.clear_user_message_data(session_id, [user1_id, user2_id])

    # Fix #10: Save warm start context so /next can boost next match quality
    session_type = "fallback" if (partner_id == _FALLBACK_PARTNER_ID) else "real"
    if quality is not None:
        await redis.set_warm_start(user_id, session_type, quality)

    # Feature 4: Send post-session exit experience message
    if bot is not None:
        lang = await get_ui_lang()
        await send_exit_experience(bot, user_id, quality, lang)

    return session_id
