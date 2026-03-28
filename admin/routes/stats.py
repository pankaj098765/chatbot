"""
admin/routes/stats.py — GET /admin/stats endpoint.

Returns a real-time snapshot of system health metrics.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from admin.auth import require_admin
from admin.database import mongodb, redis_client

router = APIRouter()


@router.get("/stats", dependencies=[Depends(require_admin)])
async def get_stats() -> dict:
    """
    Return real-time system health statistics.

    - active_users: users active in the last 24 hours
    - users_in_queue: users currently waiting for a match
    - match_success_rate: percentage of successful matches (last hour)
    - avg_wait_time: average queue wait time in seconds (last hour)
    - fallback_usage_rate: percentage of sessions using a fallback partner (last hour)
    - gender_ratio: gender distribution in the user base
    """
    users_in_queue, active_users, match_stats, fallback_rate, gender_ratio = (
        await redis_client.queue_size(),
        await mongodb.count_active_users(window_hours=24),
        await mongodb.get_match_stats(window_hours=1),
        await mongodb.get_fallback_usage_rate(window_hours=1),
        await mongodb.get_gender_ratio(),
    )

    return {
        "active_users": active_users,
        "users_in_queue": users_in_queue,
        "match_success_rate": match_stats["match_success_rate"],
        "avg_wait_time": match_stats["avg_wait_time"],
        "fallback_usage_rate": fallback_rate,
        "gender_ratio": gender_ratio,
    }
