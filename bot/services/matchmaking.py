"""
bot/services/matchmaking.py — Matchmaking engine.

Priority score formula:
  priority = (is_vip * 100) + (is_premium * 50) + (wait_time_seconds * 2) + experience_boost

Retry strategy:
  attempt 1 → strict  (language + gender filter)
  attempt 2 → relaxed (language only)
  attempt 3 → any     (no filters, just avoid recent matches)
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from bot.config import settings
from bot.database import mongodb as db
from bot.database import redis_client as redis


def calc_priority_score(user: dict, wait_seconds: float = 0.0) -> float:
    score = 0.0
    if user.get("is_vip"):
        score += 100
    if user.get("is_premium"):
        score += 50
    score += wait_seconds * 2
    # Experience boost: reward users who haven't had a recent good chat
    frustration = user.get("frustration_score", 0)
    score += min(frustration * 3, 30)   # cap at +30
    return score


async def enqueue_user(user_id: int) -> None:
    """Add a user to the matchmaking queue with their current priority score."""
    user = await db.get_user(user_id)
    if not user:
        return
    score = calc_priority_score(user)
    await redis.add_to_queue(user_id, score)
    await redis.set_search_start(user_id)


async def dequeue_user(user_id: int) -> None:
    await redis.remove_from_queue(user_id)
    await redis.clear_search_start(user_id)


async def _is_compatible(
    seeker: dict,
    candidate: dict,
    attempt: int,
) -> bool:
    """Check if two users are compatible given the attempt number (filter strictness)."""
    seeker_id = seeker["user_id"]
    candidate_id = candidate["user_id"]

    # Always avoid recent matches
    if await redis.was_recent_match(seeker_id, candidate_id):
        return False
    if await redis.was_recent_match(candidate_id, seeker_id):
        return False

    if attempt == 1:
        # Strict: language must match
        if seeker.get("language") != candidate.get("language"):
            return False
        # Gender filter (premium only): if seeker has a gender preference set
        seeker_pref = seeker.get("gender_preference")
        if seeker_pref and (seeker.get("is_premium") or seeker.get("is_vip")):
            if candidate.get("gender") != seeker_pref:
                return False
        # Reciprocal check
        cand_pref = candidate.get("gender_preference")
        if cand_pref and (candidate.get("is_premium") or candidate.get("is_vip")):
            if seeker.get("gender") != cand_pref:
                return False

    elif attempt == 2:
        # Relaxed: language only
        if seeker.get("language") != candidate.get("language"):
            return False

    # attempt 3 → no filters beyond recent-match check

    # Shadow grouping: high-abuse users match with other high-abuse users
    seeker_bad = seeker.get("bad_score", 0)
    cand_bad = candidate.get("bad_score", 0)
    threshold = settings.bad_score_threshold
    seeker_abusive = seeker_bad >= threshold // 2
    cand_abusive = cand_bad >= threshold // 2
    if seeker_abusive != cand_abusive:
        return False

    return True


async def find_match(seeker_id: int) -> Optional[int]:
    """
    Attempt to match seeker with someone in the queue.
    Tries up to 3 attempts with decreasing filter strictness.
    Returns matched partner user_id or None.
    """
    seeker = await db.get_user(seeker_id)
    if not seeker:
        return None

    candidates = await redis.get_queue_candidates(exclude_id=seeker_id, limit=50)

    for attempt in range(1, 4):
        for cand_id in candidates:
            candidate = await db.get_user(cand_id)
            if not candidate:
                continue
            if await _is_compatible(seeker, candidate, attempt):
                return cand_id

    return None
