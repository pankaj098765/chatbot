"""
admin/routes/config_routes.py — GET /admin/config and POST /admin/config/update endpoints.

Reads and writes runtime configuration stored in Redis.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from admin.auth import require_admin
from admin.database import redis_client
from config.app_config import app_config

router = APIRouter()


class ConfigUpdate(BaseModel):
    fallback_rate: float | None = None
    retry_limit: float | None = None
    priority_boost: float | None = None
    randomness_level: float | None = None
    # UPDATED: primary language configuration — admin-controlled white-label
    language_mode: str | None = None      # "english" | "native" | "mixed"
    native_language: str | None = None    # ISO 639-1 code, e.g. "hi", "es", "fr"

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

    @field_validator("language_mode")
    @classmethod
    def validate_language_mode(cls, v: str | None) -> str | None:
        valid = {"english", "native", "mixed"}
        if v is not None and v not in valid:
            raise ValueError(f"language_mode must be one of: {', '.join(sorted(valid))}")
        return v

    @field_validator("native_language")
    @classmethod
    def validate_native_language(cls, v: str | None) -> str | None:
        if v is not None and (not v.isalpha() or not (2 <= len(v) <= 3)):
            raise ValueError("native_language must be a valid ISO 639-1 language code (2-3 letters)")
        return v.lower() if v else v


@router.get("/config", dependencies=[Depends(require_admin)])
async def get_config() -> dict:
    """Return the current admin runtime configuration including static brand settings."""
    cfg = await redis_client.get_admin_config()
    # Expose read-only brand fields so the dashboard can display them
    cfg["brand_name"] = app_config.brand_name
    cfg["ai_enabled"] = app_config.ai_enabled
    cfg["payment_enabled"] = app_config.payment_enabled
    return cfg


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
