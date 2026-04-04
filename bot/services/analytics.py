"""
bot/services/analytics.py — Analytics and metrics tracking.

All write operations are fire-and-forget (asyncio.create_task) to avoid
blocking the main bot loop.

Metrics tracked:
  - match attempts (success / failure)
  - session stats (duration, message count)
  - user churn events
  - feedback ratings

Query via get_stats() for a snapshot of key KPIs.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone, timedelta

from bot.database import mongodb as db


def _fire(coro) -> None:
    """Schedule a coroutine as a background task (fire-and-forget)."""
    asyncio.create_task(coro)


# ─── Event writers ────────────────────────────────────────────────────────────

async def _write_event(event: str, data: dict) -> None:
    try:
        await db.insert_analytics_event(event, data)
    except Exception:
        pass


def track_match_attempt(user_id: int, success: bool, wait_time: float) -> None:
    _fire(_write_event("match_attempt", {
        "user_id": user_id,
        "success": success,
        "wait_time": wait_time,
    }))


def track_session(session_id: str, duration: float, message_count: int) -> None:
    _fire(_write_event("session_end", {
        "session_id": session_id,
        "duration": duration,
        "message_count": message_count,
    }))


def track_churn(user_id: int) -> None:
    _fire(_write_event("churn", {"user_id": user_id}))


def track_feedback(user_id: int, rating: str) -> None:
    _fire(_write_event("feedback", {"user_id": user_id, "rating": rating}))


# ─── Aggregated stats ─────────────────────────────────────────────────────────

async def get_stats() -> dict:
    """
    Return a dict with key platform KPIs computed over the last hour.
    """
    coll = await db.get_analytics_collection()
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

    # Match attempts in the last hour
    pipeline_matches = [
        {"$match": {"event": "match_attempt", "ts": {"$gte": one_hour_ago}}},
        {
            "$group": {
                "_id": None,
                "total": {"$sum": 1},
                "successes": {"$sum": {"$cond": ["$data.success", 1, 0]}},
                "avg_wait": {"$avg": "$data.wait_time"},
            }
        },
    ]
    match_result = await coll.aggregate(pipeline_matches).to_list(1)
    match_row = match_result[0] if match_result else {}

    total_attempts = match_row.get("total", 0)
    successes = match_row.get("successes", 0)
    success_rate = (successes / total_attempts * 100) if total_attempts else None
    avg_wait = match_row.get("avg_wait") or 0.0

    # Session stats in the last hour
    pipeline_sessions = [
        {"$match": {"event": "session_end", "ts": {"$gte": one_hour_ago}}},
        {
            "$group": {
                "_id": None,
                "avg_duration": {"$avg": "$data.duration"},
                "avg_messages": {"$avg": "$data.message_count"},
                "count": {"$sum": 1},
            }
        },
    ]
    session_result = await coll.aggregate(pipeline_sessions).to_list(1)
    session_row = session_result[0] if session_result else {}

    # Churn count in the last hour
    churn_count = await coll.count_documents(
        {"event": "churn", "ts": {"$gte": one_hour_ago}}
    )

    return {
        "matches_per_hour": total_attempts,
        "success_rate_pct": round(success_rate, 1) if success_rate is not None else None,
        "avg_wait_time_sec": round(avg_wait, 1),
        "avg_session_duration_sec": round(session_row.get("avg_duration") or 0.0, 1),
        "avg_messages_per_session": round(session_row.get("avg_messages") or 0.0, 1),
        "sessions_last_hour": session_row.get("count", 0),
        "churn_last_hour": churn_count,
    }
