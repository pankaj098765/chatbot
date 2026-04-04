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

# UPDATED
Feature 3: Tracks gender distribution in the queue (male_waiting / female_waiting
           / gender_ratio) so matchmaking can apply imbalance correction.
Feature 10: Adaptive System Tuning — adjusts admin config (fallback_rate,
            retry_limit) based on current queue health metrics.
"""
from __future__ import annotations

import asyncio
import logging
import time

from bot.database import mongodb as db
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

    # UPDATED Feature 3: Includes gender distribution (male_waiting,
    female_waiting, gender_ratio) and caches it for matchmaking use.
    """
    # Queue depth
    total_waiting: int = await redis.queue_size()

    # Average wait time across all current queue members
    searching_users = await redis.get_all_searching_users()
    wait_times: list[float] = []
    now = time.time()

    # Feature 3: Gender distribution in queue
    male_count = 0
    female_count = 0

    for uid in searching_users:
        start_ts = await redis.get_search_start_time(uid)
        if start_ts is not None:
            wait_times.append(now - start_ts)

        # Feature 3: Look up gender for each queued user
        try:
            user_doc = await db.get_user(uid)
            if user_doc:
                gender = user_doc.get("gender")
                if gender == "male":
                    male_count += 1
                elif gender == "female":
                    female_count += 1
        except Exception:
            pass

    avg_wait_time = sum(wait_times) / len(wait_times) if wait_times else 0.0

    # Match success rate from analytics (last hour)
    try:
        analytics = await get_stats()
        raw_rate = analytics.get("success_rate_pct")
        match_success_rate = raw_rate / 100.0 if raw_rate is not None else 1.0
    except Exception:
        match_success_rate = 1.0

    # Feature 3: Compute gender ratio (1.0 = balanced; > 1 = male-heavy)
    if female_count > 0:
        gender_ratio = male_count / female_count
    elif male_count == 0:
        gender_ratio = 1.0   # queue empty or all unknown → treat as balanced
    else:
        gender_ratio = 10.0  # no females, cap at sentinel high value

    stats = {
        "total_waiting": total_waiting,
        "avg_wait_time": round(avg_wait_time, 2),
        "match_success_rate": round(match_success_rate, 3),
        "male_waiting": male_count,         # Feature 3
        "female_waiting": female_count,      # Feature 3
        "gender_ratio": round(gender_ratio, 2),  # Feature 3
    }

    await redis.update_queue_stats(stats)

    # Feature 3: Cache gender counts for fast access by matchmaking
    await redis.set_gender_queue_stats(male_count, female_count)

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


async def _apply_adaptive_tuning(stats: dict) -> None:
    """
    # NEW Feature 10: Auto-adjust admin config based on queue health metrics.

    Rules:
      - avg_wait_time high  → increase fallback_rate (route more to fallback sooner)
      - avg_wait_time low   → gradually lower fallback_rate back toward baseline
      - success_rate low    → increase retry_limit (try harder before giving up)
      - success_rate high   → reduce retry_limit to save latency
    """
    try:
        from bot.services.admin_control import get_config, update_config

        config = await get_config()
        avg_wait: float = float(stats.get("avg_wait_time", 0.0))
        success_rate: float = float(stats.get("match_success_rate", 1.0))

        current_fallback_rate: float = float(config.get("fallback_rate", 0.10))
        current_retry_limit: int = int(config.get("retry_limit", 3))

        if avg_wait > _HIGH_WAIT_THRESHOLD:
            new_rate = min(0.30, current_fallback_rate + 0.05)
            if new_rate != current_fallback_rate:
                await update_config("fallback_rate", new_rate)
                logger.debug("Adaptive tuning: fallback_rate → %.2f", new_rate)
        elif avg_wait < 20.0:
            new_rate = max(0.05, current_fallback_rate - 0.02)
            if new_rate != current_fallback_rate:
                await update_config("fallback_rate", new_rate)
                logger.debug("Adaptive tuning: fallback_rate → %.2f", new_rate)

        if success_rate < _LOW_SUCCESS_THRESHOLD:
            new_limit = min(5, current_retry_limit + 1)
            if new_limit != current_retry_limit:
                await update_config("retry_limit", new_limit)
                logger.debug("Adaptive tuning: retry_limit → %d", new_limit)
        elif success_rate > 0.80:
            new_limit = max(2, current_retry_limit - 1)
            if new_limit != current_retry_limit:
                await update_config("retry_limit", new_limit)
                logger.debug("Adaptive tuning: retry_limit → %d", new_limit)

    except Exception as exc:
        logger.debug("Adaptive tuning skipped: %s", exc)


async def run_queue_monitor() -> None:
    """
    Fix #7: Long-running background coroutine that periodically collects
    queue health stats and logs warnings when thresholds are breached.

    # UPDATED Feature 10: Also calls apply_adaptive_tuning() to auto-adjust
    admin config (fallback_rate, retry_limit) based on current queue health.

    Launch via asyncio.create_task() in main.py startup hook.
    """
    logger.info("Queue monitor started (interval=%ds)", _MONITOR_INTERVAL_SECONDS)
    while True:
        try:
            stats = await collect_queue_stats()
            logger.debug("Queue stats: %s", stats)

            if stats["total_waiting"] > 0 and should_use_fallback_early(stats):
                logger.warning(
                    "Queue health degraded — total_waiting=%d avg_wait=%.1fs success_rate=%.0f%%",
                    stats["total_waiting"],
                    stats["avg_wait_time"],
                    stats["match_success_rate"] * 100,
                )

            # Feature 3: Log gender imbalance warnings
            gender_ratio = stats.get("gender_ratio", 1.0)
            if isinstance(gender_ratio, (int, float)) and gender_ratio > 3.0:
                logger.warning(
                    "Queue gender imbalance — male=%d female=%d ratio=%.1f",
                    stats.get("male_waiting", 0),
                    stats.get("female_waiting", 0),
                    gender_ratio,
                )

            # Feature 10: Adaptive system tuning
            await _apply_adaptive_tuning(stats)

        except Exception as exc:
            logger.warning("Queue monitor error: %s", exc)
        await asyncio.sleep(_MONITOR_INTERVAL_SECONDS)
