"""
admin/auth.py — Bearer-token authentication for the admin API with IP session support.

Pass the token either as:
  Authorization: Bearer <ADMIN_TOKEN>
or as a query parameter:
  ?token=<ADMIN_TOKEN>

After a successful token authentication the client IP is recorded in Redis for
IP_SESSION_TTL seconds (8 hours).  Subsequent requests from the same IP are
allowed without re-supplying the token, so the dashboard stays connected after
a page refresh without asking for the password again.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from admin.config import settings
from admin.database import redis_client

_bearer = HTTPBearer(auto_error=False)


def _get_client_ip(request: Request) -> str:
    """Extract the real client IP, honouring X-Forwarded-For proxy headers."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return ""


async def require_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    token: str | None = Query(default=None),
) -> None:
    """FastAPI dependency that enforces admin authentication.

    Accepts:
    1. A valid admin token (Bearer header or ?token= query param). On success the
       client IP receives an 8-hour trusted session so subsequent requests from the
       same IP do not need the token.
    2. A request from an IP that already has an active session (no token required).
    """
    provided = (credentials.credentials if credentials else None) or token
    client_ip = _get_client_ip(request)

    if provided == settings.admin_token:
        # Valid token — create/refresh the IP session
        if client_ip:
            await redis_client.create_ip_session(client_ip)
        return

    if provided:
        # Token was supplied but it is wrong — reject immediately
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # No token supplied — accept if the IP has an active session
    if client_ip and await redis_client.check_ip_session(client_ip):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing admin token",
        headers={"WWW-Authenticate": "Bearer"},
    )
