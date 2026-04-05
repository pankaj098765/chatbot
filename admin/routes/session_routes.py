"""
admin/routes/session_routes.py — IP session status and logout endpoints.

These routes are intentionally NOT protected by require_admin so the dashboard
can check session state without already having a token.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from admin.auth import _get_client_ip, require_admin
from admin.database import redis_client

router = APIRouter()


@router.get("/session/status")
async def session_status(request: Request) -> dict:
    """
    Return whether the current client IP has an active admin session.

    No authentication required — the client calls this on page load to decide
    whether to prompt for the admin token.
    """
    client_ip = _get_client_ip(request)
    if not client_ip:
        return {"active": False, "ttl": 0}
    active = await redis_client.check_ip_session(client_ip)
    if not active:
        return {"active": False, "ttl": 0}
    ttl = await redis_client.get_ip_session_ttl(client_ip)
    return {"active": True, "ttl": ttl}


@router.post("/session/logout", dependencies=[Depends(require_admin)])
async def session_logout(request: Request) -> dict:
    """Revoke the current IP session, forcing re-authentication on the next visit."""
    client_ip = _get_client_ip(request)
    if client_ip:
        await redis_client.delete_ip_session(client_ip)
    return {"detail": "Session revoked"}
