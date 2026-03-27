"""
bot/services/anti_abuse.py — Anti-abuse and spam detection system.

Scoring per user (cumulative bad_score stored in MongoDB):
  Spam (repeated messages in window)  : +2
  Abuse word detected                  : +3
  Instant disconnect (< 5 sec)         : +1

Actions when bad_score > threshold:
  - Reduce priority score in queue
  - Increase wait time via Redis cooldown
  - Shadow-group: high-score users match with other high-score users
    (handled by matchmaking compatibility check)
"""
from __future__ import annotations

from bot.config import settings
from bot.database import mongodb as db
from bot.database import redis_client as redis

# Minimum words that constitute a "real" message vs possible spam
_MIN_MESSAGE_LEN = 1

# Basic list of abuse keywords (extend as needed)
_ABUSE_WORDS: frozenset[str] = frozenset(
    {
        "fuck", "bitch", "asshole", "bastard", "slut", "whore",
        "nigger", "faggot", "retard", "cunt",
    }
)


def _contains_abuse(text: str) -> bool:
    lowered = text.lower().split()
    return bool(_ABUSE_WORDS.intersection(lowered))


async def check_and_score_message(user_id: int, text: str) -> int:
    """
    Evaluate a message for spam/abuse.
    Increments bad_score accordingly.
    Returns the current bad_score.
    """
    added = 0

    # Spam detection via rolling window
    msg_count_in_window = await redis.record_message_timestamp(user_id)
    if msg_count_in_window > settings.spam_message_limit:
        added += 2

    # Abuse word detection
    if _contains_abuse(text):
        added += 3

    if added > 0:
        await db.increment_user(user_id, {"bad_score": added})

    user = await db.get_user(user_id)
    bad_score = user.get("bad_score", 0) if user else 0

    # Apply cooldown if threshold exceeded
    if bad_score >= settings.bad_score_threshold:
        await redis.set_abuse_cooldown(user_id, ttl_seconds=300)  # 5-min cooldown

    return bad_score


async def record_instant_disconnect(user_id: int, session_duration: float) -> None:
    """Penalise users who disconnect almost immediately (< 5 seconds)."""
    if session_duration < 5.0:
        await db.increment_user(user_id, {"bad_score": 1})
        user = await db.get_user(user_id)
        bad_score = user.get("bad_score", 0) if user else 0
        if bad_score >= settings.bad_score_threshold:
            await redis.set_abuse_cooldown(user_id, ttl_seconds=300)


async def is_blocked(user_id: int) -> bool:
    """Return True if user is currently in an abuse cooldown."""
    return await redis.is_in_abuse_cooldown(user_id)


async def get_bad_score(user_id: int) -> int:
    user = await db.get_user(user_id)
    return user.get("bad_score", 0) if user else 0
