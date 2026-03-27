"""
bot/services/fallback.py — Simulated fallback partner engine.

Triggered when:
  - No real match found after all retry attempts
  - OR experience engine returns "FALLBACK"

Runs an async background task that sends variable-delay responses
for 2–8 minutes then ends naturally.
"""
from __future__ import annotations

import asyncio
import time

from aiogram import Bot

from bot.ai.behavior import BehaviorController
from bot.database import redis_client as redis
from bot.utils.helpers import generate_session_id

# Fake partner user_id used as the Redis key placeholder for fallback sessions
_FALLBACK_PARTNER_ID = -1


async def start_fallback_session(bot: Bot, user_id: int) -> None:
    """
    Start a simulated fallback chat session for user_id.
    Runs as a fire-and-forget asyncio task.
    """
    session_id = generate_session_id()
    controller = BehaviorController()
    start_time = time.time()
    message_count = 0

    # Signal that user is "connected" to the fallback partner
    await redis.set_session(user_id, _FALLBACK_PARTNER_ID, session_id)

    # Opening message after a short delay
    await asyncio.sleep(controller.get_delay())
    try:
        await bot.send_message(user_id, "Hey! 👋")
        message_count += 1
    except Exception:
        await redis.clear_session(user_id)
        return

    # Main response loop
    while True:
        duration = time.time() - start_time

        if controller.should_exit(duration, message_count):
            break

        await asyncio.sleep(controller.get_delay())

        try:
            response = controller.generate_response()
            await bot.send_message(user_id, response)
            message_count += 1
        except Exception:
            break

    # Natural exit
    try:
        exit_msg = controller.exit_message()
        await bot.send_message(user_id, exit_msg)
        await bot.send_message(
            user_id,
            "Your partner has disconnected.\n\nTap /search to find a new stranger!",
        )
    except Exception:
        pass

    await redis.clear_session(user_id)


def launch_fallback(bot: Bot, user_id: int) -> None:
    """Schedule the fallback session as a background asyncio task."""
    asyncio.create_task(start_fallback_session(bot, user_id))
