"""
bot/services/session.py — Session lifecycle management.

Manages:
  - Creating sessions (Redis hot-state + MongoDB persistence)
  - Relaying messages between partners
  - Ending sessions with outcome tracking
"""
from __future__ import annotations

import time
from typing import Optional

from aiogram import Bot

from bot.database import mongodb as db
from bot.database import redis_client as redis
from bot.utils.helpers import generate_session_id


async def create_session(bot: Bot, user1_id: int, user2_id: int) -> str:
    """Create a new session between two users. Returns session_id."""
    session_id = generate_session_id()
    # Store hot-state in Redis
    await redis.set_session(user1_id, user2_id, session_id)
    # Persist to MongoDB
    await db.create_session(session_id, user1_id, user2_id)
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


async def end_session(
    user_id: int,
    exit_reason: str = "user_stop",
    quality: str | None = None,
) -> Optional[str]:
    """
    End the session for user_id (and their partner).
    Returns the session_id if a session existed, else None.
    """
    session_id = await redis.get_session_id(user_id)
    if not session_id:
        return None

    msg_count = await redis.get_message_count(session_id)
    # Retrieve the session start time from Redis search_start as a proxy
    elapsed = await redis.get_search_elapsed(user_id)

    # Determine quality from session stats if not provided
    if quality is None:
        if elapsed > 120 and msg_count >= 5:
            quality = "GOOD_CHAT"
        elif elapsed < 20 or msg_count == 0:
            quality = "BAD_CHAT"

    await db.end_session(
        session_id=session_id,
        exit_reason=exit_reason,
        message_count=msg_count,
        duration=elapsed,
        quality=quality,
    )
    await redis.clear_session(user_id)
    await redis.clear_message_count(session_id)

    return session_id
