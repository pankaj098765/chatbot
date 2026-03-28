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

# UPDATED
Feature 2:  Global Persona Usage Tracking (anti-detection) — adjusts persona
            selection weights so no single persona dominates globally.
Feature 5:  First-session experience boost — forces longer minimum duration and
            lower randomness for users on their very first session.
Feature 6:  Randomness Limiter — reads randomness_level from admin config and
            passes it to BehaviorController.
Feature 9:  Global Pattern Breaker — avoids reusing the same persona/style that
            was recorded as the last global pattern.
Ultra-human upgrade:
  - generate_response() now returns list[str]; bursts are sent with short delays.
  - Typing action (chat_action) is sent before each message for realism.
  - New "playful" persona is included in rotation.
"""
from __future__ import annotations

import asyncio
import random
import time

from aiogram import Bot
from aiogram.enums import ChatAction

from bot.ai.behavior import BehaviorController
from bot.ai.personas import PERSONAS
from bot.database import mongodb as db
from bot.database import redis_client as redis
from bot.services import admin_control
from bot.utils.helpers import generate_session_id

# Fake partner user_id used as the Redis key placeholder for fallback sessions
_FALLBACK_PARTNER_ID = -1

# Feature 5: Minimum session duration (seconds) for a first-session user
_FIRST_SESSION_MIN_DURATION = 180.0


# ─── Persona selection ────────────────────────────────────────────────────────

async def _pick_persona(user_id: int, global_patterns: dict) -> str:
    """
    # UPDATED (Feature 2 + Feature 9)
    Pick a persona that:
    1. Was NOT used in the user's last two sessions  (Fix #5)
    2. Is NOT the last globally used persona          (Feature 9 – pattern breaker)
    3. Favours under-represented personas globally    (Feature 2 – anti-detection)
    """
    user = await db.get_user(user_id)
    last_personas: list[str] = []
    if user:
        last_personas = list(user.get("last_personas_used", []))

    # Feature 9: exclude the last global persona to break patterns
    last_global_persona = global_patterns.get("last_persona", "")

    all_names = list(PERSONAS.keys())

    # Feature 2: Anti-detection weights — underused personas get higher weight
    global_usage: dict[str, int] = await redis.get_all_persona_usage()
    total_usage = sum(global_usage.values()) or 1

    available_names: list[str] = []
    adjusted_weights: list[float] = []

    for name in all_names:
        # Exclude user's recent personas (Fix #5)
        if name in last_personas[-2:]:
            continue
        # Exclude last global persona when alternatives exist (Feature 9)
        if name == last_global_persona and len(all_names) > 1:
            continue
        usage_ratio = global_usage.get(name, 0) / total_usage
        # Weight: base weight scaled down proportionally to how overused the persona is.
        # The 2× multiplier means a persona used by 50% of sessions gets weight 0
        # (floor-clamped to 0.1), creating strong pressure to rotate personas evenly.
        w = max(0.1, PERSONAS[name].weight * (1.0 - usage_ratio * 2.0))
        available_names.append(name)
        adjusted_weights.append(w)

    if not available_names:
        # Fallback: all candidates excluded — reset to full list with base weights
        available_names = all_names
        adjusted_weights = [PERSONAS[n].weight for n in all_names]

    chosen = random.choices(available_names, weights=adjusted_weights, k=1)[0]

    # Feature 2: Increment global usage counter for the chosen persona
    await redis.increment_persona_usage(chosen)

    return chosen


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


async def _send_with_typing(bot: Bot, user_id: int, text: str) -> None:
    """Send a typing action then the message, mimicking a real user typing."""
    await bot.send_chat_action(user_id, ChatAction.TYPING)
    # Brief pause to let the typing indicator show
    await asyncio.sleep(random.uniform(0.4, 1.2))
    await bot.send_message(user_id, text)


async def start_fallback_session(bot: Bot, user_id: int) -> None:
    """
    Start a simulated fallback chat session for user_id.
    Runs as a fire-and-forget asyncio task.

    # UPDATED
    Feature 2: Uses global-aware persona picker (anti-detection).
    Feature 5: Extends minimum duration for first-session users.
    Feature 6: Reads randomness_level from admin config.
    Feature 9: Reads and updates global patterns to avoid repetition.
    Tone system: Derives tone from user's gender profile (female → "feminine",
                 male → "masculine", unset → "neutral"); tone is passed to
                 BehaviorController and stored in session for consistency.
    Ultra-human: Handles list[str] bursts from generate_response(); sends
                 typing indicators before each message.
    """
    session_id = generate_session_id()

    # Feature 6: Read admin config for randomness_level
    try:
        config = await admin_control.get_config()
        randomness_level: float = float(config.get("randomness_level", 0.5))
    except Exception:
        randomness_level = 0.5

    # Feature 5: Detect first-session user and reduce randomness
    user = await db.get_user(user_id)
    is_first_session = bool(user and user.get("total_searches", 0) == 0)
    if is_first_session:
        randomness_level = 0.3  # low variance → more predictable / pleasant

    # Tone system: derive tone from the user's gender stored in their profile
    gender = user.get("gender") if user else None
    if gender == "female":
        tone = "feminine"
    elif gender == "male":
        tone = "masculine"
    else:
        tone = "neutral"

    # Feature 9: Read current global patterns before picking persona
    global_patterns = await redis.get_global_patterns()

    # Feature 2 + Fix #5 + Feature 9: Pick persona with global awareness
    persona_name = await _pick_persona(user_id, global_patterns)
    controller = BehaviorController(
        persona_name=persona_name,
        randomness_level=randomness_level,  # Feature 6
        tone=tone,                          # Tone system
    )
    await _record_persona_used(user_id, persona_name)

    # Feature 9: Update global patterns for next session to diverge from
    await redis.set_global_patterns(controller.current_pattern)

    start_time = time.time()
    message_count = 0

    # Signal that user is "connected" to the fallback partner; store tone
    await redis.set_session(user_id, _FALLBACK_PARTNER_ID, session_id)
    await redis.set_session_tone(user_id, tone)

    # Opening message after a short delay
    await asyncio.sleep(controller.get_delay())
    try:
        await _send_with_typing(bot, user_id, "Hey! 👋")
        message_count += 1
    except Exception:
        await redis.clear_session(user_id)
        return

    # Main response loop
    while True:
        duration = time.time() - start_time

        # Feature 5: First-session users get a guaranteed minimum duration
        if is_first_session and duration < _FIRST_SESSION_MIN_DURATION:
            pass  # skip exit check until minimum duration is reached
        elif controller.should_exit(duration, message_count):
            break

        await asyncio.sleep(controller.get_delay())

        try:
            messages = controller.generate_response()
            # generate_response() may return an empty list (question-ignore)
            for i, msg in enumerate(messages):
                if i > 0:
                    # Brief human-like pause between burst messages
                    await asyncio.sleep(controller.get_burst_delay())
                await _send_with_typing(bot, user_id, msg)
                message_count += 1
        except Exception:
            break

    # Natural exit
    try:
        exit_msg = controller.exit_message()
        await _send_with_typing(bot, user_id, exit_msg)
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
