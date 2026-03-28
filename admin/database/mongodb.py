"""
admin/database/mongodb.py — Async MongoDB helpers for the admin dashboard.

Uses the same collections as bot/database/mongodb.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import motor.motor_asyncio

from admin.config import settings

_client: motor.motor_asyncio.AsyncIOMotorClient | None = None
_db: motor.motor_asyncio.AsyncIOMotorDatabase | None = None


async def connect() -> None:
    global _client, _db
    _client = motor.motor_asyncio.AsyncIOMotorClient(settings.mongodb_uri)
    _db = _client[settings.db_name]


async def disconnect() -> None:
    if _client:
        _client.close()


def _users() -> motor.motor_asyncio.AsyncIOMotorCollection:
    assert _db is not None, "MongoDB not connected"
    return _db.users


def _sessions() -> motor.motor_asyncio.AsyncIOMotorCollection:
    assert _db is not None, "MongoDB not connected"
    return _db.sessions


def _analytics() -> motor.motor_asyncio.AsyncIOMotorCollection:
    assert _db is not None, "MongoDB not connected"
    return _db.analytics


async def count_active_users(window_hours: int = 24) -> int:
    """Count users whose last_active timestamp is within the given window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    return await _users().count_documents({"last_active": {"$gte": cutoff}})


async def get_match_stats(window_hours: int = 1) -> dict:
    """Return match success rate and average wait time from the analytics collection."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    pipeline = [
        {"$match": {"event": "match_attempt", "ts": {"$gte": cutoff}}},
        {
            "$group": {
                "_id": None,
                "total": {"$sum": 1},
                "successes": {"$sum": {"$cond": ["$data.success", 1, 0]}},
                "avg_wait": {"$avg": "$data.wait_time"},
            }
        },
    ]
    result = await _analytics().aggregate(pipeline).to_list(1)
    row = result[0] if result else {}
    total = row.get("total", 0)
    successes = row.get("successes", 0)
    return {
        "total_attempts": total,
        "match_success_rate": round((successes / total * 100) if total else 0.0, 1),
        "avg_wait_time": round(row.get("avg_wait") or 0.0, 1),
    }


async def get_fallback_usage_rate(window_hours: int = 1) -> float:
    """Return the percentage of sessions that used a fallback partner."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    total = await _sessions().count_documents({"started_at": {"$gte": cutoff}})
    if total == 0:
        return 0.0
    fallback = await _sessions().count_documents(
        {"started_at": {"$gte": cutoff}, "is_fallback": True}
    )
    return round(fallback / total * 100, 1)


async def get_gender_ratio() -> dict[str, int]:
    """Return gender distribution of all registered users."""
    pipeline = [
        {"$group": {"_id": "$gender", "count": {"$sum": 1}}},
    ]
    rows = await _users().aggregate(pipeline).to_list(10)
    result: dict[str, int] = {"male": 0, "female": 0, "unknown": 0}
    for row in rows:
        key = row["_id"] or "unknown"
        result[key] = row["count"]
    return result
