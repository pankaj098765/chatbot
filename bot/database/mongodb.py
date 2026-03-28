"""
bot/database/mongodb.py — Async MongoDB client and data access layer.

Collections:
  users    — one document per Telegram user
  sessions — one document per chat session
  analytics — aggregate event records
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import motor.motor_asyncio

from bot.config import settings

_client: motor.motor_asyncio.AsyncIOMotorClient | None = None
_db: motor.motor_asyncio.AsyncIOMotorDatabase | None = None


async def connect() -> None:
    """Initialize the Motor client and create indexes."""
    global _client, _db
    _client = motor.motor_asyncio.AsyncIOMotorClient(settings.mongodb_uri)
    _db = _client[settings.db_name]
    # Indexes for common queries
    await _db.users.create_index("user_id", unique=True)
    await _db.sessions.create_index("session_id", unique=True)
    await _db.sessions.create_index([("user1_id", 1), ("user2_id", 1)])
    await _db.analytics.create_index("event")


async def disconnect() -> None:
    """Close the Motor client."""
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


# ─── User helpers ────────────────────────────────────────────────────────────

async def get_user(user_id: int) -> dict | None:
    return await _users().find_one({"user_id": user_id}, {"_id": 0})


async def create_user(user_id: int, username: str | None = None) -> dict:
    """Insert a new user document with sensible defaults."""
    doc: dict[str, Any] = {
        "user_id": user_id,
        "username": username,
        "gender": None,          # "male" | "female" | None
        "language": "en",
        "is_premium": False,
        "is_vip": False,
        "premium_expires": None,
        "vip_expires": None,
        "created_at": datetime.now(timezone.utc),
        "last_active": datetime.now(timezone.utc),
        # Abuse / matchmaking
        "bad_score": 0,
        "priority_score": 0,
        # Experience engine
        "total_searches": 0,
        "success_count": 0,
        "last_5_results": [],     # rolling list of "GOOD_CHAT"|"BAD_CHAT"|"FAIL"
        "avg_session_time": 0.0,
        "frustration_score": 0,
        # Fix #1: Match quality feedback loop
        "positive_feedback_count": 0,
        "negative_feedback_count": 0,
        # Fix #3: Churn detection
        "last_3_session_durations": [],
        "avg_session_duration": 0.0,
        "churn_risk": "LOW",      # "LOW" | "HIGH"
        # Fix #5: Session diversity
        "last_personas_used": [],
        # Fix #9: Intent detection
        "intent": None,           # "gender_check" | None
        # Feature 8: Emotional state detection (NEW)
        "emotional_state": "neutral",   # "satisfied" | "neutral" | "frustrated"
        # Feature 1: Last session engagement score (NEW)
        "last_engagement_score": 0.0,
    }
    await _users().insert_one(doc)
    doc.pop("_id", None)
    return doc


async def get_or_create_user(user_id: int, username: str | None = None) -> dict:
    user = await get_user(user_id)
    if user is None:
        user = await create_user(user_id, username)
    return user


async def update_user(user_id: int, updates: dict) -> None:
    await _users().update_one({"user_id": user_id}, {"$set": updates})


async def increment_user(user_id: int, increments: dict) -> None:
    await _users().update_one({"user_id": user_id}, {"$inc": increments})


# ─── Session helpers ──────────────────────────────────────────────────────────

async def create_session(
    session_id: str,
    user1_id: int,
    user2_id: int,
    tone: str = "neutral",
) -> dict:
    doc: dict[str, Any] = {
        "session_id": session_id,
        "user1_id": user1_id,
        "user2_id": user2_id,
        "started_at": datetime.now(timezone.utc),
        "ended_at": None,
        "message_count": 0,
        "duration": 0.0,
        "exit_reason": None,
        "quality": None,          # "GOOD_CHAT" | "BAD_CHAT" | None
        "is_fallback": False,
        "engagement_score": 0.0,  # Feature 1: computed on session end (NEW)
        "tone": tone,             # "feminine" | "neutral" | "masculine"
    }
    await _sessions().insert_one(doc)
    doc.pop("_id", None)
    return doc


async def get_session(session_id: str) -> dict | None:
    return await _sessions().find_one({"session_id": session_id}, {"_id": 0})


async def end_session(
    session_id: str,
    exit_reason: str,
    message_count: int,
    duration: float,
    quality: str | None = None,
) -> None:
    await _sessions().update_one(
        {"session_id": session_id},
        {
            "$set": {
                "ended_at": datetime.now(timezone.utc),
                "exit_reason": exit_reason,
                "message_count": message_count,
                "duration": duration,
                "quality": quality,
            }
        },
    )


async def update_session(session_id: str, updates: dict) -> None:
    await _sessions().update_one({"session_id": session_id}, {"$set": updates})


async def increment_session_messages(session_id: str) -> None:
    await _sessions().update_one(
        {"session_id": session_id}, {"$inc": {"message_count": 1}}
    )


# ─── Analytics helpers ────────────────────────────────────────────────────────

async def insert_analytics_event(event: str, data: dict) -> None:
    doc = {
        "event": event,
        "data": data,
        "ts": datetime.now(timezone.utc),
    }
    await _analytics().insert_one(doc)


async def get_analytics_collection() -> motor.motor_asyncio.AsyncIOMotorCollection:
    return _analytics()
