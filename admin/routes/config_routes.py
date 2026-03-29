"""
admin/routes/config_routes.py — GET /admin/config and POST /admin/config/update endpoints.

Reads and writes runtime configuration stored in Redis.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from admin.auth import require_admin
from admin.database import redis_client
from bot.i18n.languages import SUPPORTED_LANGUAGES
from bot.services.admin_control import get_config as get_admin_config
from config.app_config import app_config

router = APIRouter()

# ─── Language presets ─────────────────────────────────────────────────────────
# Each preset atomically sets ui_language, chat_language, and language_mode so
# buyers can switch the whole bot to a supported language in one step.

LANGUAGE_PRESETS: dict[str, dict[str, str]] = {
    "english": {
        "language_mode": "english",
        "native_language": "en",
        "ui_language": "en",
        "chat_language": "en",
    },
    "spanish": {
        "language_mode": "native",
        "native_language": "es",
        "ui_language": "es",
        "chat_language": "es",
    },
    "hindi": {
        "language_mode": "native",
        "native_language": "hi",
        "ui_language": "hi",
        "chat_language": "hi",
    },
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _validate_language_combination(
    language_mode: str,
    native_language: str,
    ui_language: str | None,
    chat_language: str | None,
) -> None:
    """
    Raise HTTPException 422 for invalid language combinations.

    Rules:
    - "native" or "mixed" mode requires a non-English native_language.
    - "english" mode must not set ui_language or chat_language to a non-English code.
    """
    if language_mode in ("native", "mixed") and native_language == "en":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"language_mode='{language_mode}' requires a non-English native_language. "
                "Use language_mode='english' for English-only mode, or set a non-English "
                "native_language (e.g. 'hi', 'es')."
            ),
        )
    if language_mode == "english":
        for field_name, lang_code in (
            ("ui_language", ui_language),
            ("chat_language", chat_language),
        ):
            if lang_code is not None and lang_code != "en":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"{field_name}='{lang_code}' conflicts with language_mode='english'. "
                        f"Set {field_name}='en' or switch to a non-English language_mode."
                    ),
                )


class ConfigUpdate(BaseModel):
    fallback_rate: float | None = None
    retry_limit: float | None = None
    priority_boost: float | None = None
    randomness_level: float | None = None
    # UPDATED: primary language configuration — admin-controlled white-label
    language_mode: str | None = None      # "english" | "native" | "mixed"
    native_language: str | None = None    # ISO 639-1 code, e.g. "hi", "es", "fr"
    # Separate UI vs AI language channels
    ui_language: str | None = None        # ISO 639-1 code for buttons/menus
    chat_language: str | None = None      # ISO 639-1 code for LLM/AI responses

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
        if v is None:
            return v
        v = v.strip().lower()
        if v not in SUPPORTED_LANGUAGES:
            supported = ", ".join(sorted(SUPPORTED_LANGUAGES.keys()))
            raise ValueError(
                f"native_language '{v}' is not supported. "
                f"Must be one of: {supported}"
            )
        return v

    @field_validator("ui_language")
    @classmethod
    def validate_ui_language(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in SUPPORTED_LANGUAGES:
            supported = ", ".join(sorted(SUPPORTED_LANGUAGES.keys()))
            raise ValueError(
                f"ui_language '{v}' is not supported. Must be one of: {supported}"
            )
        return v

    @field_validator("chat_language")
    @classmethod
    def validate_chat_language(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in SUPPORTED_LANGUAGES:
            supported = ", ".join(sorted(SUPPORTED_LANGUAGES.keys()))
            raise ValueError(
                f"chat_language '{v}' is not supported. Must be one of: {supported}"
            )
        return v


@router.get("/languages", dependencies=[Depends(require_admin)])
async def get_languages() -> dict:
    """Return the full map of supported language codes to display names."""
    return {"languages": SUPPORTED_LANGUAGES}


@router.get("/config/presets", dependencies=[Depends(require_admin)])
async def get_presets() -> dict:
    """Return available language presets with their settings."""
    return {"presets": LANGUAGE_PRESETS}


@router.post("/config/preset", dependencies=[Depends(require_admin)])
async def apply_preset(body: dict) -> dict:
    """
    Apply a named language preset, atomically setting language_mode,
    native_language, ui_language, and chat_language.

    Body: {"preset": "english" | "spanish" | "hindi"}
    Returns the full config after the update.
    """
    preset_name: str = (body.get("preset") or "").strip().lower()
    if preset_name not in LANGUAGE_PRESETS:
        available = ", ".join(sorted(LANGUAGE_PRESETS.keys()))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown preset '{preset_name}'. Available presets: {available}",
        )
    await redis_client.set_admin_config_bulk(LANGUAGE_PRESETS[preset_name])
    cfg = await redis_client.get_admin_config()
    cfg["brand_name"] = app_config.brand_name
    cfg["ai_enabled"] = app_config.ai_enabled
    cfg["payment_enabled"] = app_config.payment_enabled
    return cfg


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
    Cross-field safety check prevents invalid language combinations.
    Returns the full config after the update.
    """
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No config fields provided",
        )

    # Safety check: validate language combination against merged state.
    # For ui_language and chat_language only include the value if it is part
    # of this request — otherwise the validator would reject existing configs
    # that were set under a different language_mode.
    current = await get_admin_config()
    merged_mode = str(updates.get("language_mode", current.get("language_mode", "english")))
    merged_native = str(updates.get("native_language", current.get("native_language", "en")))
    merged_ui: str | None = updates.get("ui_language")
    merged_chat: str | None = updates.get("chat_language")
    _validate_language_combination(merged_mode, merged_native, merged_ui, merged_chat)

    await redis_client.set_admin_config_bulk(updates)
    return await redis_client.get_admin_config()
