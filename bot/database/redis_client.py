"""
bot/database/redis_client.py — Async Redis client for hot-state and queue management.

Key namespaces:
  user:state:{user_id}          → FSM state string
  user:search_start:{user_id}   → Unix timestamp when search started
  queue                         → Sorted set; score = priority_score
  session:{user_id}             → partner user_id
  session_id:{user_id}          → session_id string
  recent_matches:{user_id}      → Set of recent partner user_ids
  abuse:spam:{user_id}          → List of message timestamps (rolling window)
  abuse:cooldown:{user_id}      → TTL key marking cooldown
"""
from __future__ import annotations

import time
from typing import Optional

import redis.asyncio as aioredis

from bot.config import settings

_redis: aioredis.Redis | None = None


async def connect() -> None:
    global _redis
    _redis = aioredis.from_url(settings.redis_url, decode_responses=True)


async def disconnect() -> None:
    if _redis:
        await _redis.aclose()


def _r() -> aioredis.Redis:
    assert _redis is not None, "Redis not connected"
    return _redis


# ─── User state ───────────────────────────────────────────────────────────────

async def set_user_state(user_id: int, state: str) -> None:
    await _r().set(f"user:state:{user_id}", state)


async def get_user_state(user_id: int) -> str | None:
    return await _r().get(f"user:state:{user_id}")


async def delete_user_state(user_id: int) -> None:
    await _r().delete(f"user:state:{user_id}")


# ─── Search timestamp ─────────────────────────────────────────────────────────

async def set_search_start(user_id: int) -> None:
    await _r().set(f"user:search_start:{user_id}", str(time.time()))


async def get_search_elapsed(user_id: int) -> float:
    val = await _r().get(f"user:search_start:{user_id}")
    if val is None:
        return 0.0
    return time.time() - float(val)


async def clear_search_start(user_id: int) -> None:
    await _r().delete(f"user:search_start:{user_id}")


# ─── Matchmaking queue ────────────────────────────────────────────────────────

QUEUE_KEY = "matchmaking_queue"


async def add_to_queue(user_id: int, priority_score: float) -> None:
    await _r().zadd(QUEUE_KEY, {str(user_id): priority_score})


async def remove_from_queue(user_id: int) -> None:
    await _r().zrem(QUEUE_KEY, str(user_id))


async def queue_size() -> int:
    return await _r().zcard(QUEUE_KEY)


async def get_queue_candidates(exclude_id: int, limit: int = 50) -> list[int]:
    """Return up to `limit` user IDs from the queue, highest priority first, excluding `exclude_id`."""
    members = await _r().zrevrange(QUEUE_KEY, 0, limit + 1)
    return [int(m) for m in members if int(m) != exclude_id]


# ─── Session mapping ──────────────────────────────────────────────────────────

async def set_session(user_id: int, partner_id: int, session_id: str) -> None:
    pipe = _r().pipeline()
    pipe.set(f"session:{user_id}", str(partner_id))
    pipe.set(f"session:{partner_id}", str(user_id))
    pipe.set(f"session_id:{user_id}", session_id)
    pipe.set(f"session_id:{partner_id}", session_id)
    await pipe.execute()


async def get_partner(user_id: int) -> Optional[int]:
    val = await _r().get(f"session:{user_id}")
    return int(val) if val else None


async def get_session_id(user_id: int) -> str | None:
    return await _r().get(f"session_id:{user_id}")


async def clear_session(user_id: int) -> None:
    partner_id = await get_partner(user_id)
    pipe = _r().pipeline()
    pipe.delete(f"session:{user_id}")
    pipe.delete(f"session_id:{user_id}")
    if partner_id:
        pipe.delete(f"session:{partner_id}")
        pipe.delete(f"session_id:{partner_id}")
    await pipe.execute()


# ─── Session message counter ─────────────────────────────────────────────────

async def increment_message_count(session_id: str) -> int:
    return await _r().incr(f"msg_count:{session_id}")


async def get_message_count(session_id: str) -> int:
    val = await _r().get(f"msg_count:{session_id}")
    return int(val) if val else 0


async def clear_message_count(session_id: str) -> None:
    await _r().delete(f"msg_count:{session_id}")


# ─── Recent matches ──────────────────────────────────────────────────────────

async def add_recent_match(user_id: int, partner_id: int, ttl: int = 3600) -> None:
    key = f"recent_matches:{user_id}"
    await _r().sadd(key, str(partner_id))
    await _r().expire(key, ttl)


async def was_recent_match(user_id: int, partner_id: int) -> bool:
    return await _r().sismember(f"recent_matches:{user_id}", str(partner_id))


# ─── Abuse / cooldown ────────────────────────────────────────────────────────

async def record_message_timestamp(user_id: int) -> int:
    """Push current timestamp, return count in the last spam window."""
    key = f"abuse:spam:{user_id}"
    now = time.time()
    pipe = _r().pipeline()
    pipe.lpush(key, str(now))
    pipe.ltrim(key, 0, settings.spam_message_limit + 5)
    pipe.expire(key, settings.spam_window_seconds)
    await pipe.execute()
    timestamps = await _r().lrange(key, 0, -1)
    cutoff = now - settings.spam_window_seconds
    return sum(1 for ts in timestamps if float(ts) > cutoff)


async def set_abuse_cooldown(user_id: int, ttl_seconds: int = 300) -> None:
    await _r().set(f"abuse:cooldown:{user_id}", "1", ex=ttl_seconds)


async def is_in_abuse_cooldown(user_id: int) -> bool:
    return bool(await _r().exists(f"abuse:cooldown:{user_id}"))


# ─── Watchdog (Fix #8: Soft failure recovery) ────────────────────────────────

async def get_all_searching_users() -> list[int]:
    """Return all user IDs currently in the matchmaking queue."""
    members = await _r().zrange(QUEUE_KEY, 0, -1)
    return [int(m) for m in members]


async def get_search_start_time(user_id: int) -> float | None:
    """Return the Unix timestamp when the user started searching, or None."""
    val = await _r().get(f"user:search_start:{user_id}")
    return float(val) if val else None


# ─── Queue stats (Fix #7: Queue health monitor) ──────────────────────────────

QUEUE_STATS_KEY = "queue:stats"


async def update_queue_stats(stats: dict) -> None:
    """Persist queue health stats as a Redis hash."""
    await _r().hset(QUEUE_STATS_KEY, mapping={k: str(v) for k, v in stats.items()})
    await _r().expire(QUEUE_STATS_KEY, 300)


async def get_queue_stats() -> dict:
    """Retrieve queue health stats."""
    raw = await _r().hgetall(QUEUE_STATS_KEY)
    result: dict = {}
    for k, v in raw.items():
        try:
            result[k] = float(v)
        except (ValueError, TypeError):
            result[k] = v
    return result


# ─── Warm start context (Fix #10) ────────────────────────────────────────────

async def set_warm_start(user_id: int, session_type: str, outcome: str) -> None:
    pipe = _r().pipeline()
    pipe.set(f"warm_start:type:{user_id}", session_type, ex=3600)
    pipe.set(f"warm_start:outcome:{user_id}", outcome, ex=3600)
    await pipe.execute()


async def get_warm_start(user_id: int) -> dict | None:
    pipe = _r().pipeline()
    pipe.get(f"warm_start:type:{user_id}")
    pipe.get(f"warm_start:outcome:{user_id}")
    results = await pipe.execute()
    if not results[0]:
        return None
    return {"session_type": results[0], "outcome": results[1]}
