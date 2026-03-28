"""
bot/services/experience.py — Experience Engine.

Decides what should happen next for a user based on their match history:
  "MATCH_REAL"  → attempt a real-user match (normal path)
  "RETRY"       → re-queue with relaxed filters (still real)
  "FALLBACK"    → use the simulated fallback partner

Frustration scoring (over last_5_results)
------------------------------------------
  +2 per FAIL result
  +3 per BAD_CHAT
  -2 per GOOD_CHAT
  Clamped to 0 on the lower end.

Rules (evaluated in priority order)
--------------------------------------
1. total_searches <= 3   → MATCH_REAL  (new-user grace period / Fix #4)
2. frustration >= 5      → MATCH_REAL  (rescue frustrated user)
3. last 2 == FAIL        → MATCH_REAL  (consecutive failure fix)
4. >=4 GOOD in last 5    → 50% RETRY / 50% FALLBACK  (inject variety)
5. Probabilistic default → 70% MATCH_REAL / 20% RETRY / 10% FALLBACK

Churn Detection (Fix #3)
------------------------------------------
  Tracks last_3_session_durations.
  If avg_session_duration < 20s → churn_risk = HIGH.
"""
from __future__ import annotations

import random
from typing import Literal

from bot.database import mongodb as db

Outcome = Literal["GOOD_CHAT", "BAD_CHAT", "FAIL"]
Action = Literal["MATCH_REAL", "RETRY", "FALLBACK"]

_P_MATCH_REAL = 0.70
_P_RETRY_CUTOFF = 0.90

# Fix #3: Churn risk threshold (seconds)
_CHURN_DURATION_THRESHOLD = 20.0


def _calc_frustration(last_5: list[str]) -> int:
    score = 0
    for result in last_5:
        if result == "FAIL":
            score += 2
        elif result == "BAD_CHAT":
            score += 3
        elif result == "GOOD_CHAT":
            score -= 2
    return max(0, score)


def decide_next_action(user: dict) -> Action:
    """Decide what the matchmaking service should do next for this user."""
    total = user.get("total_searches", 0)
    last_5: list[str] = user.get("last_5_results", [])
    frustration = _calc_frustration(last_5)

    # Rule 1 — new-user grace period (also satisfies Fix #4)
    if total <= 3:
        return "MATCH_REAL"

    # Rule 2 — frustrated user, give a real match to restore confidence
    if frustration >= 5:
        return "MATCH_REAL"

    # Rule 3 — two consecutive failures
    if len(last_5) >= 2 and last_5[-1] == "FAIL" and last_5[-2] == "FAIL":
        return "MATCH_REAL"

    # Fix #3 — high churn risk: force a real high-quality match
    if user.get("churn_risk") == "HIGH":
        return "MATCH_REAL"

    # Rule 4 — very satisfied user: inject variety to avoid monotony
    good_count = last_5.count("GOOD_CHAT")
    if good_count >= 4:
        return random.choice(["RETRY", "FALLBACK"])

    # Rule 5 — probabilistic default
    roll = random.random()
    if roll < _P_MATCH_REAL:
        return "MATCH_REAL"
    elif roll < _P_RETRY_CUTOFF:
        return "RETRY"
    else:
        return "FALLBACK"


async def record_outcome(
    user_id: int,
    outcome: Outcome,
    session_duration: float | None = None,
) -> None:
    """
    Persist a match outcome and recalculate the frustration score.

    Updates:
      - last_5_results (rolling window of 5)
      - frustration_score
      - success_count (incremented on GOOD_CHAT)
      - total_searches (always incremented)
      - last_3_session_durations + avg_session_duration + churn_risk (Fix #3)
    """
    user = await db.get_user(user_id)
    if not user:
        return

    last_5: list[str] = list(user.get("last_5_results", []))
    last_5.append(outcome)
    if len(last_5) > 5:
        last_5 = last_5[-5:]

    frustration = _calc_frustration(last_5)

    updates: dict = {
        "last_5_results": last_5,
        "frustration_score": frustration,
    }
    increments: dict = {"total_searches": 1}
    if outcome == "GOOD_CHAT":
        increments["success_count"] = 1

    # Fix #3: Churn detection — track rolling window of last 3 session durations
    if session_duration is not None:
        durations: list[float] = list(user.get("last_3_session_durations", []))
        durations.append(session_duration)
        if len(durations) > 3:
            durations = durations[-3:]
        avg_dur = sum(durations) / len(durations)
        churn_risk = "HIGH" if avg_dur < _CHURN_DURATION_THRESHOLD else "LOW"
        updates["last_3_session_durations"] = durations
        updates["avg_session_duration"] = avg_dur
        updates["churn_risk"] = churn_risk

    await db.update_user(user_id, updates)
    await db.increment_user(user_id, increments)


async def update_feedback_score(user_id: int, positive: bool) -> None:
    """
    Fix #1: Update feedback counters after a session rating.
    These counters feed directly into the matchmaking priority score.
    """
    if positive:
        await db.increment_user(user_id, {"positive_feedback_count": 1})
    else:
        await db.increment_user(user_id, {"negative_feedback_count": 1})
