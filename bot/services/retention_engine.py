"""
bot/services/retention_engine.py — Retention and churn prevention engine.

Responsibilities:
  - Fix #3:  Detect high-churn-risk users from session duration history.
  - Fix #8:  Watchdog — detect users stuck in SEARCHING state > 30 seconds
             and reset them back to queue automatically.
  - Fix #10: Warm-start context retrieval to boost priority on /next.

This module is called from:
  - search handler (warm start boost on /next)
  - a periodic background task started in main.py (watchdog)
"""
from __future__ import annotations

import asyncio
import logging
import time

from aiogram import Bot

from bot.database import mongodb as db
from bot.database import redis_client as redis
from bot.services import matchmaking

logger = logging.getLogger(__name__)

# Fix #8: Users stuck searching longer than this are reset
_WATCHDOG_TIMEOUT_SECONDS = 30
# How often the watchdog scans the queue (seconds)
_WATCHDOG_INTERVAL_SECONDS = 15


# ─── Fix #10: Warm start ─────────────────────────────────────────────────────

async def get_warm_start_boost(user_id: int) -> float:
    """
    Return a priority score boost for a user who just pressed /next.

    Boost logic:
      - Previous session was GOOD_CHAT with a real partner → +30 (keep momentum)
      - Previous session was BAD_CHAT → +60 (compensate bad experience)
      - No warm start context → 0
    """
    ctx = await redis.get_warm_start(user_id)
    if not ctx:
        return 0.0
    outcome = ctx.get("outcome", "")
    if outcome == "GOOD_CHAT":
        return 30.0
    if outcome == "BAD_CHAT":
        return 60.0
    # FAIL or unknown outcome — modest boost to keep the user in the funnel
    return 20.0


async def apply_warm_start_boost(user_id: int) -> None:
    """
    Fix #10: Re-enqueue the user with a warm-start priority boost applied.
    Called at the start of _do_search when the trigger is /next.
    """
    boost = await get_warm_start_boost(user_id)
    if boost <= 0:
        return
    user = await db.get_user(user_id)
    if not user:
        return
    base_score = matchmaking.calc_priority_score(user)
    await redis.add_to_queue(user_id, base_score + boost)
    logger.debug("Warm-start boost +%.0f applied to user %d", boost, user_id)

# ─── Fix #8: Watchdog ────────────────────────────────────────────────────────

async def _watchdog_tick() -> None:
    """
    Scan all users in the matchmaking queue.
    Any user whose search has exceeded _WATCHDOG_TIMEOUT_SECONDS without a match
    is dequeued and re-added with a refreshed priority score (soft reset).
    """
    searching_users = await redis.get_all_searching_users()
    now = time.time()

    for user_id in searching_users:
        start_ts = await redis.get_search_start_time(user_id)
        if start_ts is None:
            continue
        elapsed = now - start_ts
        if elapsed > _WATCHDOG_TIMEOUT_SECONDS:
            logger.info(
                "Watchdog: user %d stuck in SEARCHING for %.1fs — re-queuing",
                user_id,
                elapsed,
            )
            # Remove stale entry and re-add with a refreshed (boosted) score
            await redis.remove_from_queue(user_id)
            user = await db.get_user(user_id)
            if user:
                new_score = matchmaking.calc_priority_score(user, wait_seconds=elapsed)
                await redis.add_to_queue(user_id, new_score)
                await redis.set_search_start(user_id)  # reset timer


async def run_watchdog(bot: Bot) -> None:
    """
    Fix #8: Long-running background coroutine that periodically checks for
    users stuck in the SEARCHING state and rescues them.

    Launch via asyncio.create_task() in main.py startup hook.
    """
    logger.info("Retention watchdog started (interval=%ds)", _WATCHDOG_INTERVAL_SECONDS)
    while True:
        try:
            await _watchdog_tick()
        except Exception as exc:
            logger.warning("Watchdog error: %s", exc)
        await asyncio.sleep(_WATCHDOG_INTERVAL_SECONDS)
