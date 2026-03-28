"""
bot/services/queue_monitor.py — Queue health monitoring system.

Fix #7: Tracks live queue health statistics and uses them to dynamically
adjust matchmaking behavior (retry timing, fallback thresholds).

Stats collected:
  total_waiting      — number of users currently in the queue
  avg_wait_time      — average seconds users have been waiting
  match_success_rate — fraction of recent match attempts that succeeded (0–1)

Effects on matchmaking:
  - High avg_wait_time  → lower fallback trigger threshold (help users sooner)
  - Low  success_rate   → shorten poll timeout to avoid long waits
  - Low  total_waiting  → accept FALLBACK sooner to avoid lonely queue
"""
from __future__ import annotations

import asyncio
import logging
import time

from bot.database import redis_client as redis
from bot.services.analytics import get_stats

logger = logging.getLogger(__name__)

# How often queue stats are refreshed (seconds)
_MONITOR_INTERVAL_SECONDS = 30

# Thresholds that drive adaptive behavior
_HIGH_WAIT_THRESHOLD = 45.0      # avg_wait_time (seconds) considered "high"
_LOW_SUCCESS_THRESHOLD = 0.40    # match_success_rate below this is "low"
_LOW_QUEUE_THRESHOLD = 3         # fewer than this many users → nearly empty


async def collect_queue_stats() -> dict:
    """
    Compute and return current queue health stats.
    Also persists them to Redis so other services can read them cheaply.
    """
    # Queue depth
    total_waiting: int = await redis.queue_size()

    # Average wait time across all current queue members
    searching_users = await redis.get_all_searching_users()
    wait_times: list[float] = []
    now = time.time()
    for uid in searching_users:
        start_ts = await redis.get_search_start_time(uid)
        if start_ts is not None:
            wait_times.append(now - start_ts)
    avg_wait_time = sum(wait_times) / len(wait_times) if wait_times else 0.0

    # Match success rate from analytics (last hour)
    try:
        analytics = await get_stats()
        raw_rate = analytics.get("success_rate_pct", 100.0)
        match_success_rate = raw_rate / 100.0
    except Exception:
        match_success_rate = 1.0

    stats = {
        "total_waiting": total_waiting,
        "avg_wait_time": round(avg_wait_time, 2),
        "match_success_rate": round(match_success_rate, 3),
    }

    await redis.update_queue_stats(stats)
    return stats


def should_use_fallback_early(stats: dict) -> bool:
    """
    Return True if queue conditions are poor enough that we should trigger
    the fallback simulation sooner than normal.
    """
    if stats.get("total_waiting", 0) < _LOW_QUEUE_THRESHOLD:
        return True
    if stats.get("avg_wait_time", 0.0) > _HIGH_WAIT_THRESHOLD:
        return True
    if stats.get("match_success_rate", 1.0) < _LOW_SUCCESS_THRESHOLD:
        return True
    return False


def get_adaptive_poll_timeout(stats: dict, default_timeout: int) -> int:
    """
    Return an adjusted max wait time (seconds) based on current queue health.
    Under poor conditions, reduce the timeout to avoid making users wait too long.
    """
    if should_use_fallback_early(stats):
        return max(20, default_timeout // 2)
    return default_timeout


async def run_queue_monitor() -> None:
    """
    Fix #7: Long-running background coroutine that periodically collects
    queue health stats and logs warnings when thresholds are breached.

    Launch via asyncio.create_task() in main.py startup hook.
    """
    logger.info("Queue monitor started (interval=%ds)", _MONITOR_INTERVAL_SECONDS)
    while True:
        try:
            stats = await collect_queue_stats()
            logger.debug("Queue stats: %s", stats)
            if should_use_fallback_early(stats):
                logger.warning(
                    "Queue health degraded — total_waiting=%d avg_wait=%.1fs success_rate=%.0f%%",
                    stats["total_waiting"],
                    stats["avg_wait_time"],
                    stats["match_success_rate"] * 100,
                )
        except Exception as exc:
            logger.warning("Queue monitor error: %s", exc)
        await asyncio.sleep(_MONITOR_INTERVAL_SECONDS)
