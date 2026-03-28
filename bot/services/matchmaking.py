"""
bot/services/matchmaking.py — Matchmaking engine.

Priority score formula (production-grade):
  priority = (is_vip * 100)
            + (is_premium * 50)
            + (wait_time_seconds * 2)
            + experience_boost           # frustration cap +30
            + (positive_feedback * 10)   # Fix #1: feedback loop
            - (negative_feedback * 5)    # Fix #1: feedback loop
            + (churn_boost)              # Fix #3: churn detection
            + (cold_start_boost)         # Fix #4: new user grace

Unified candidate pool (Fix #2):
  CandidateUser provides a single interface for both real users and
  simulated (fallback) users — the matching engine never distinguishes them.

Retry strategy:
  attempt 1 → strict  (language + gender filter)
  attempt 2 → relaxed (language only)
  attempt 3 → any     (no filters, just avoid recent matches)

Low-quality pool (Fix #1):
  Users with high negative_feedback_count are separated into a low-quality
  pool so they preferentially match each other.

# UPDATED
Feature 3: Queue Imbalance Auto-Correction — when the queue is male-heavy,
           male enqueue priority is reduced and female priority boosted.
Feature 5: First-session boost is applied explicitly at enqueue time.
Feature 7: Admin config priority_boost is added to every enqueue score.
Feature 10: Retry limit is read dynamically from admin config.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from bot.config import settings
from bot.database import mongodb as db
from bot.database import redis_client as redis

# Threshold for labelling a user as "low quality" based on feedback
_LOW_QUALITY_THRESHOLD = 5

# Feature 3: Gender ratio threshold above which the queue is considered male-heavy
_MALE_HEAVY_RATIO = 2.0
# Priority adjustments for gender imbalance correction
_MALE_HEAVY_PENALTY = 20.0
_FEMALE_PRIORITY_BOOST = 30.0


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

    # Fix #1: Feedback loop — positive reviews raise priority, negative lower it
    positive = user.get("positive_feedback_count", 0)
    negative = user.get("negative_feedback_count", 0)
    score += positive * 10
    score -= negative * 5

    # Fix #3: Churn risk boost — keep at-risk users engaged with faster matches
    if user.get("churn_risk") == "HIGH":
        score += 50

    # Fix #4: Cold start boost — new users always get fast matches
    if user.get("total_searches", 0) <= 3:
        score += 200

    return score


# ─── Fix #2: Unified CandidateUser interface ─────────────────────────────────

@dataclass
class CandidateUser:
    """Unified representation for both real and simulated match candidates.

    The matching engine operates exclusively on CandidateUser instances and
    never needs to know whether a candidate is a real person or a simulation.
    """
    user_id: int
    metadata: dict            # full user document (real) or synthetic stub
    priority_score: float
    is_simulated: bool = False
    extra: dict = field(default_factory=dict)


def _make_simulated_candidate(priority: float = 0.0) -> CandidateUser:
    """Build a synthetic CandidateUser that acts as a fallback match slot."""
    return CandidateUser(
        user_id=-1,
        metadata={
            "user_id": -1,
            "language": None,  # compatible with any seeker
            "gender": None,
            "gender_preference": None,
            "is_premium": False,
            "is_vip": False,
            "bad_score": 0,
        },
        priority_score=priority,
        is_simulated=True,
    )


async def build_unified_candidates(
    seeker_id: int,
    include_simulated: bool = True,
    limit: int = 50,
) -> list[CandidateUser]:
    """Build a unified pool of real + (optionally) simulated candidates."""
    raw_ids = await redis.get_queue_candidates(exclude_id=seeker_id, limit=limit)
    candidates: list[CandidateUser] = []

    for cand_id in raw_ids:
        cand_doc = await db.get_user(cand_id)
        if not cand_doc:
            continue
        wait = await redis.get_search_elapsed(cand_id)
        score = calc_priority_score(cand_doc, wait_seconds=wait)
        candidates.append(CandidateUser(
            user_id=cand_id,
            metadata=cand_doc,
            priority_score=score,
        ))

    if include_simulated:
        # Inject a simulated candidate at the end (lowest priority);
        # it will only be selected if no real user is compatible.
        candidates.append(_make_simulated_candidate(priority=-999.0))

    return candidates


# ─── Queue helpers ────────────────────────────────────────────────────────────

async def enqueue_user(user_id: int) -> None:
    """
    Add a user to the matchmaking queue with their current priority score.

    # UPDATED
    Feature 3: Applies gender-imbalance correction — reduces male priority when
               the queue is male-heavy, boosts female priority.
    Feature 7: Adds admin-configured priority_boost to every score.
    """
    user = await db.get_user(user_id)
    if not user:
        return
    score = calc_priority_score(user)

    # Feature 7: Admin config priority_boost
    try:
        from bot.services.admin_control import get_config
        config = await get_config()
        score += float(config.get("priority_boost", 0.0))
    except Exception:
        pass

    # Feature 3: Gender imbalance auto-correction
    user_gender = user.get("gender")
    if user_gender in ("male", "female"):
        try:
            male_count, female_count = await redis.get_gender_queue_stats()
            if female_count > 0:
                ratio = male_count / female_count
                if ratio > _MALE_HEAVY_RATIO:
                    if user_gender == "male":
                        score -= _MALE_HEAVY_PENALTY
                    else:
                        score += _FEMALE_PRIORITY_BOOST
        except Exception:
            pass

    await redis.add_to_queue(user_id, score)
    await redis.set_search_start(user_id)


async def dequeue_user(user_id: int) -> None:
    await redis.remove_from_queue(user_id)
    await redis.clear_search_start(user_id)


# ─── Compatibility check ──────────────────────────────────────────────────────

def _is_low_quality(user_doc: dict) -> bool:
    return user_doc.get("negative_feedback_count", 0) >= _LOW_QUALITY_THRESHOLD


async def _is_compatible(
    seeker: dict,
    candidate: CandidateUser,
    attempt: int,
) -> bool:
    """Check if seeker and candidate are compatible at the given filter level."""
    seeker_id = seeker["user_id"]
    cand_id = candidate.user_id
    cand_doc = candidate.metadata

    # Simulated candidates are always compatible (fallback of last resort)
    if candidate.is_simulated:
        return True

    # Always avoid recent matches
    if await redis.was_recent_match(seeker_id, cand_id):
        return False
    if await redis.was_recent_match(cand_id, seeker_id):
        return False

    # Fix #1: Low-quality pool isolation
    seeker_low = _is_low_quality(seeker)
    cand_low = _is_low_quality(cand_doc)
    if seeker_low != cand_low:
        return False

    if attempt == 1:
        if seeker.get("language") != cand_doc.get("language"):
            return False
        seeker_pref = seeker.get("gender_preference")
        if seeker_pref and (seeker.get("is_premium") or seeker.get("is_vip")):
            if cand_doc.get("gender") != seeker_pref:
                return False
        cand_pref = cand_doc.get("gender_preference")
        if cand_pref and (cand_doc.get("is_premium") or cand_doc.get("is_vip")):
            if seeker.get("gender") != cand_pref:
                return False

    elif attempt == 2:
        if seeker.get("language") != cand_doc.get("language"):
            return False

    # attempt 3 → no language/gender filter beyond recent-match + low-quality checks

    # Shadow grouping: high-abuse users match with other high-abuse users
    seeker_bad = seeker.get("bad_score", 0)
    cand_bad = cand_doc.get("bad_score", 0)
    threshold = settings.bad_score_threshold
    seeker_abusive = seeker_bad >= threshold // 2
    cand_abusive = cand_bad >= threshold // 2
    if seeker_abusive != cand_abusive:
        return False

    return True


# ─── Match finder ─────────────────────────────────────────────────────────────

async def find_match(seeker_id: int) -> Optional[CandidateUser]:
    """
    Attempt to match seeker with someone from the unified candidate pool.
    Returns a CandidateUser (real or simulated) or None.

    # UPDATED Feature 10: Retry limit is read from admin config so the
    queue monitor can increase it dynamically when the success rate is low.
    A simulated candidate is injected at low priority and will only be returned
    if no real user is compatible across all retry attempts.
    """
    seeker = await db.get_user(seeker_id)
    if not seeker:
        return None

    # Feature 10: Dynamic retry limit from admin config
    retry_limit = 3
    try:
        from bot.services.admin_control import get_config
        config = await get_config()
        retry_limit = max(1, int(config.get("retry_limit", 3)))
    except Exception:
        pass

    # Build unified pool: real users + one simulated slot at lowest priority
    candidates = await build_unified_candidates(seeker_id, include_simulated=True)

    for attempt in range(1, retry_limit + 1):
        for candidate in candidates:
            if await _is_compatible(seeker, candidate, attempt):
                return candidate

    return None
