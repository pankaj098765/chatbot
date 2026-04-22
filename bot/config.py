"""
bot/config.py — Central configuration loaded from environment variables.

Priority (highest to lowest):
  1. Environment variables  — set by the shell / Docker / cloud platform
  2. .env file              — loaded only as a fallback (override=False)
  3. Default values         — hard-coded sensible defaults per field

The .env file is *optional*: if it is absent no error is raised.

LLM provider / key resolution order (just set LLM_API_KEY — nothing else needed):
  1. LLM_PROVIDER  + LLM_API_KEY          — fully explicit
  2. LLM_API_KEY alone                    — provider auto-detected from key format:
       sk-ant-… → anthropic  |  gsk_… → groq     |  AIza… → gemini
       xai-…   → grok        |  sk-…  → openai   (default for unrecognised formats)
  3. LLM_PROVIDER  + <PROVIDER>_API_KEY   — provider set, key via provider-specific var
     e.g.  LLM_PROVIDER=gemini  + GEMINI_API_KEY=…
  4. Auto-detect from provider-specific key with no LLM_PROVIDER set:
     GEMINI_API_KEY / ANTHROPIC_API_KEY / GROQ_API_KEY / GROK_API_KEY /
     MISTRAL_API_KEY / DEEPSEEK_API_KEY / TOGETHER_API_KEY
  5. LLM_PROVIDER=openai  + OPENAI_API_KEY (legacy alias)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load .env only as a fallback — existing env vars are NEVER overwritten.
# dotenv returns False silently when the file is missing, so this is safe.
load_dotenv(override=False)

# Ordered mapping: provider-specific env-var name → provider identifier.
# Used both for explicit-provider key lookup (step 2) and auto-detection (step 3).
# Order matters for auto-detection priority.
_PROVIDER_KEY_ENVS: dict[str, str] = {
    "GEMINI_API_KEY":    "gemini",
    "ANTHROPIC_API_KEY": "anthropic",
    "GROQ_API_KEY":      "groq",
    "GROK_API_KEY":      "grok",
    "MISTRAL_API_KEY":   "mistral",
    "DEEPSEEK_API_KEY":  "deepseek",
    "TOGETHER_API_KEY":  "together",
    # OPENAI_API_KEY is handled separately as a legacy alias below
}

logger = logging.getLogger(__name__)


def get_env(key: str, default: str = "", required: bool = False) -> str:
    """Return the value of *key* from the environment (or *default*).

    Raises ``ValueError`` when *required* is ``True`` and no value is found.
    Always returns a ``str``; pass ``default=""`` to get an empty string
    when the key is absent.
    """
    value = os.getenv(key) or default
    if required and not value:
        raise ValueError(f"Missing required environment variable: {key}")
    return value


@dataclass(frozen=True)
class Settings:
    bot_token: str
    mongodb_uri: str
    redis_url: str
    db_name: str
    debug: bool

    # Anti-abuse thresholds
    bad_score_threshold: int = 10
    spam_window_seconds: int = 60
    spam_message_limit: int = 10

    # Matchmaking
    queue_poll_interval: float = 1.0   # seconds between queue polls
    max_wait_seconds: int = 120        # max time in queue before fallback

    # Payment — Telegram Stars (XTR)
    premium_price_stars: int = 100
    vip_price_stars: int = 250
    subscription_days: int = 30

    # LLM integration
    openai_api_key: str = ""      # legacy — still supported for OpenAI
    llm_model: str = ""           # optional — each provider has a built-in default
    llm_enabled: bool = True      # global kill-switch

    # Multi-provider LLM config
    # llm_provider: "openai" | "gemini" | "grok" | "groq" | "mistral" |
    #               "deepseek" | "anthropic" | "together" | "custom"
    llm_provider: str = "openai"
    # llm_api_key: generic key for the selected provider.
    # Falls back to openai_api_key when provider == "openai" and this is empty.
    llm_api_key: str = ""
    # llm_base_url: override the REST endpoint (required for "custom",
    # auto-populated for all built-in providers).
    llm_base_url: str = ""

    # Sponsor branding — shown as a subtle line on every disconnect message.
    # Set SPONSOR_NAME (optionally with a description after a | separator) and
    # SPONSOR_LINK in .env; leave either empty to disable the sponsor block.
    # e.g.  SPONSOR_NAME=AcmeCo|The fastest VPN on the planet
    sponsor_name: str = ""
    sponsor_link: str = ""
    sponsor_description: str = ""


# ─── Key-format fingerprints ─────────────────────────────────────────────────
# Maps a key prefix to the provider name.  Checked in order; first match wins.
# Only prefixes that are *unambiguously* tied to one provider are listed.
_KEY_FINGERPRINTS: list[tuple[str, str]] = [
    ("sk-ant-",  "anthropic"),   # Anthropic — always starts with sk-ant-
    ("gsk_",     "groq"),        # Groq
    ("AIza",     "gemini"),      # Google / Gemini
    ("xai-",     "grok"),        # xAI / Grok
    ("sk-or-",   "openrouter"),  # OpenRouter
    ("sk-",      "openai"),      # OpenAI (also used by DeepSeek, but much more common)
]


def _detect_provider_from_key(key: str) -> str | None:
    """
    Infer the AI provider from the format / prefix of the API key.

    Returns the provider name string if detected, or None when the key
    format is not recognised (caller should default to "openai" or warn).
    """
    for prefix, provider in _KEY_FINGERPRINTS:
        if key.startswith(prefix):
            return provider
    return None


def _resolve_llm_provider_and_key() -> tuple[str, str]:
    """
    Determine the effective LLM provider and API key using a multi-step
    fallback strategy.  Setting only ``LLM_API_KEY`` is sufficient — the
    provider is auto-detected from the key format when ``LLM_PROVIDER`` is
    not explicitly configured.

    Resolution order
    ----------------
    1. LLM_PROVIDER + LLM_API_KEY — fully explicit, nothing inferred.
    2. LLM_API_KEY set, LLM_PROVIDER empty — **fingerprint the key** to
       detect the provider; fall back to "openai" for unrecognised formats.
    3. LLM_PROVIDER set, LLM_API_KEY empty — check the matching provider-
       specific alias env var (e.g. GEMINI_API_KEY when LLM_PROVIDER=gemini).
    4. Neither set — scan all provider-specific alias env vars in priority
       order (GEMINI_API_KEY, ANTHROPIC_API_KEY, …) for auto-detection.
    5. Legacy: OPENAI_API_KEY when provider is openai (or still unset).

    Returns (provider, api_key).
    """
    explicit_provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    llm_api_key = os.getenv("LLM_API_KEY", "").strip()

    # Step 1 — fully explicit: both LLM_PROVIDER and LLM_API_KEY are set.
    if llm_api_key and explicit_provider:
        return explicit_provider, llm_api_key

    # Step 2 — LLM_API_KEY set but no explicit provider: fingerprint the key.
    if llm_api_key:
        detected = _detect_provider_from_key(llm_api_key)
        if detected:
            logger.info(
                "LLM provider auto-detected from API key format: %r "
                "(set LLM_PROVIDER explicitly to override)",
                detected,
            )
        else:
            logger.info(
                "LLM_API_KEY format not recognised — defaulting to provider='openai'. "
                "Set LLM_PROVIDER explicitly if you are using a different provider."
            )
        return detected or "openai", llm_api_key

    # Step 3 — LLM_PROVIDER set but LLM_API_KEY missing: check the matching
    # provider-specific env var (e.g. GEMINI_API_KEY when LLM_PROVIDER=gemini).
    if explicit_provider:
        specific_env = f"{explicit_provider.upper()}_API_KEY"
        key = os.getenv(specific_env, "").strip()
        if key:
            return explicit_provider, key

    # Step 4 — no LLM_PROVIDER set: auto-detect from available provider keys.
    if not explicit_provider:
        for env_var, provider_name in _PROVIDER_KEY_ENVS.items():
            key = os.getenv(env_var, "").strip()
            if key:
                return provider_name, key

    # Step 5 — legacy: OPENAI_API_KEY when provider is openai (or still unset).
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_key and (not explicit_provider or explicit_provider == "openai"):
        return "openai", openai_key

    # No key found; return provider (or default) with empty key so the warning
    # in llm_engine can report the correct provider name.
    return explicit_provider or "openai", ""


def _get_settings() -> Settings:
    token = get_env("BOT_TOKEN", required=True)
    llm_provider, llm_api_key = _resolve_llm_provider_and_key()
    cfg = Settings(
        bot_token=token,
        mongodb_uri=get_env("MONGODB_URI", "mongodb://localhost:27017"),
        redis_url=get_env("REDIS_URL", "redis://localhost:6379"),
        db_name=get_env("DB_NAME", "anonymous_chat"),
        debug=get_env("DEBUG", "false").lower() == "true",
        openai_api_key=get_env("OPENAI_API_KEY", ""),
        llm_model=get_env("LLM_MODEL", "").strip(),
        llm_enabled=get_env("LLM_ENABLED", "true").lower() == "true",
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        llm_base_url=get_env("LLM_BASE_URL", ""),
        sponsor_link=get_env("SPONSOR_LINK", ""),
    )
    # Parse optional description from SPONSOR_NAME using | separator.
    # e.g. SPONSOR_NAME=AcmeCo|The fastest VPN on the planet
    raw_sponsor = get_env("SPONSOR_NAME", "")
    if "|" in raw_sponsor:
        _sname, _sdesc = raw_sponsor.split("|", 1)
        cfg.sponsor_name = _sname.strip()
        cfg.sponsor_description = _sdesc.strip()
    else:
        cfg.sponsor_name = raw_sponsor.strip()
        cfg.sponsor_description = ""
    return cfg


settings = _get_settings()


def log_config_summary() -> None:
    """Log which configuration keys are set, without revealing their values."""
    # Build the display list without keeping sensitive values near log calls.
    lines: list[str] = [
        f"BOT_TOKEN: {'SET' if settings.bot_token else 'NOT SET'}",
        f"MONGODB_URI: {'SET' if settings.mongodb_uri else 'NOT SET'}",
        f"REDIS_URL: {'SET' if settings.redis_url else 'NOT SET'}",
        f"DB_NAME: {'SET' if settings.db_name else 'NOT SET'}",
        f"LLM_PROVIDER: {settings.llm_provider or 'NOT SET'} "
        f"({'key SET' if settings.llm_api_key else 'key NOT SET'})",
        f"LLM_ENABLED: {'true' if settings.llm_enabled else 'false'}",
        f"DEBUG: {'true' if settings.debug else 'false'}",
    ]
    logger.debug("Config loaded:")
    for line in lines:
        logger.debug("  - %s", line)
