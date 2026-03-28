"""
bot/services/fallback.py — Simulated fallback partner engine.

Triggered when:
  - No real match found after all retry attempts
  - OR experience engine returns "FALLBACK"

Runs an async background task that sends variable-delay responses
for 2–8 minutes then ends naturally.

Fix #5: Session Diversity Control
  Tracks last_personas_used per user and avoids repeating the same persona
  twice in a row so each session feels different.
"""
from __future__ import annotations

import asyncio
import random
import time

from aiogram import Bot

from bot.ai.behavior import BehaviorController
from bot.ai.personas import PERSONAS
from bot.database import mongodb as db
from bot.database import redis_client as redis
from bot.utils.helpers import generate_session_id

# Fake partner user_id used as the Redis key placeholder for fallback sessions
_FALLBACK_PARTNER_ID = -1


async def _pick_persona(user_id: int) -> str:
    """
    Fix #5: Pick a persona that was NOT used in the last two sessions.
    Falls back to random selection if all personas have been used recently.
    """
    user = await db.get_user(user_id)
    last_personas: list[str] = []
    if user:
        last_personas = list(user.get("last_personas_used", []))

    all_names = list(PERSONAS.keys())
    available = [p for p in all_names if p not in last_personas[-2:]]
    if not available:
        available = all_names  # all used recently, reset rotation

    # Respect persona weights for selection
    weights = [PERSONAS[p].weight for p in available]
    return random.choices(available, weights=weights, k=1)[0]


async def _record_persona_used(user_id: int, persona_name: str) -> None:
    """Fix #5: Persist the persona used so future sessions can avoid repetition."""
    user = await db.get_user(user_id)
    if not user:
        return
    last_personas: list[str] = list(user.get("last_personas_used", []))
    last_personas.append(persona_name)
    if len(last_personas) > 5:
        last_personas = last_personas[-5:]
    await db.update_user(user_id, {"last_personas_used": last_personas})


async def start_fallback_session(bot: Bot, user_id: int) -> None:
    """
    Start a simulated fallback chat session for user_id.
    Runs as a fire-and-forget asyncio task.
    """
    session_id = generate_session_id()

    # Fix #5: Choose a non-repeating persona
    persona_name = await _pick_persona(user_id)
    controller = BehaviorController(persona_name=persona_name)
    await _record_persona_used(user_id, persona_name)

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
