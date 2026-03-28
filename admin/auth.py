"""
admin/auth.py — Simple bearer-token authentication for the admin API.

Pass the token either as:
  Authorization: Bearer <ADMIN_TOKEN>
or as a query parameter:
  ?token=<ADMIN_TOKEN>
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from admin.config import settings

_bearer = HTTPBearer(auto_error=False)


async def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    token: str | None = Query(default=None),
) -> None:
    """FastAPI dependency that enforces admin authentication."""
    provided = (credentials.credentials if credentials else None) or token
    if provided != settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token",
            headers={"WWW-Authenticate": "Bearer"},
        )
