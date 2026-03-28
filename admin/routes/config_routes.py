"""
admin/routes/config_routes.py — GET /admin/config and POST /admin/config/update endpoints.

Reads and writes runtime configuration stored in Redis.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from admin.auth import require_admin
from admin.database import redis_client

router = APIRouter()


class ConfigUpdate(BaseModel):
    fallback_rate: float | None = None
    retry_limit: float | None = None
    priority_boost: float | None = None
    randomness_level: float | None = None

    @field_validator("fallback_rate")
    @classmethod
    def validate_fallback_rate(cls, v: float | None) -> float | None:
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError("fallback_rate must be between 0.0 and 1.0")
        return v

    @field_validator("retry_limit")
    @classmethod
    def validate_retry_limit(cls, v: float | None) -> float | None:
        if v is not None and not (1 <= v <= 10):
            raise ValueError("retry_limit must be between 1 and 10")
        return v

    @field_validator("priority_boost")
    @classmethod
    def validate_priority_boost(cls, v: float | None) -> float | None:
        if v is not None and not (0.0 <= v <= 200.0):
            raise ValueError("priority_boost must be between 0 and 200")
        return v

    @field_validator("randomness_level")
    @classmethod
    def validate_randomness_level(cls, v: float | None) -> float | None:
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError("randomness_level must be between 0.0 and 1.0")
        return v


@router.get("/config", dependencies=[Depends(require_admin)])
async def get_config() -> dict:
    """Return the current admin runtime configuration."""
    return await redis_client.get_admin_config()


@router.post("/config/update", dependencies=[Depends(require_admin)])
async def update_config(body: ConfigUpdate) -> dict:
    """
    Update one or more admin config values.

    Only the fields provided in the request body will be updated.
    Returns the full config after the update.
    """
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No config fields provided",
        )
    await redis_client.set_admin_config_bulk(updates)
    return await redis_client.get_admin_config()
