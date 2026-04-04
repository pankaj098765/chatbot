"""
bot/ai/llm_engine.py — LLM-powered multilingual response generator.

Supports multiple AI providers via a provider-agnostic adapter layer:

  Provider        | How connected
  --------------- | -----------------------------------------------
  openai          | openai.AsyncOpenAI (default base_url)
  gemini          | openai.AsyncOpenAI + Google OpenAI-compat endpoint
  grok            | openai.AsyncOpenAI + xAI endpoint
  groq            | openai.AsyncOpenAI + Groq endpoint
  mistral         | openai.AsyncOpenAI + Mistral endpoint
  deepseek        | openai.AsyncOpenAI + DeepSeek endpoint
  together        | openai.AsyncOpenAI + Together AI endpoint
  anthropic       | anthropic.AsyncAnthropic (separate SDK)
  custom          | openai.AsyncOpenAI + LLM_BASE_URL (self-hosted / any compat API)

Configuration (environment variables):
  LLM_PROVIDER    — one of the names above (default: auto-detected from key format)
  LLM_API_KEY     — API key for the selected provider
  LLM_MODEL       — model name (optional; auto-discovered from provider's /models API)
  LLM_BASE_URL    — only required for "custom"; auto-set for all built-in providers
  OPENAI_API_KEY  — legacy alias, used when LLM_PROVIDER=openai and LLM_API_KEY unset

Design principles:
  - Async-safe; lazy client init
  - Non-blocking: always returns None on failure so callers fall back gracefully
  - Short output: prompt constrains LLM to 1–2 lines; response is hard-clamped
  - Anti-detection: applies random typo / shortening / message split after LLM
  - Filter: strips AI-sounding phrases and overly formal language
  - Zero hardcoding: model is discovered at runtime via the provider's models API
"""
from __future__ import annotations

import logging
import random
import re

from bot.config import settings
from config.app_config import app_config

logger = logging.getLogger(__name__)

# ─── Provider routing table ───────────────────────────────────────────────────
# Maps provider name → OpenAI-compatible base_url.
# Providers listed here are all handled via the openai SDK with a custom base_url.
# "anthropic" is absent because it requires its own SDK.
_OPENAI_COMPAT_PROVIDERS: dict[str, str] = {
    "openai":    "",          # uses library default
    "gemini":    "https://generativelanguage.googleapis.com/v1beta/openai/",
    "grok":      "https://api.x.ai/v1",
    "groq":      "https://api.groq.com/openai/v1",
    "mistral":   "https://api.mistral.ai/v1",
    "deepseek":  "https://api.deepseek.com/v1",
    "together":  "https://api.together.xyz/v1",
    "custom":    "",          # filled at runtime from LLM_BASE_URL
}

# ─── Model discovery ─────────────────────────────────────────────────────────
# Model is discovered at runtime by querying the provider's /models endpoint.
# No model names are hardcoded — the bot adapts to whatever the provider offers.

# Substrings that indicate a model is NOT suitable for chat completion.
_NON_CHAT_KEYWORDS: tuple[str, ...] = (
    "embed", "embedding",
    "whisper", "transcri",
    "tts", "speech",
    "dall-e", "image",
    "moderation",
    "text-search", "text-similarity",
    "babbage", "davinci-002",   # legacy completion-only
    "instruct",                 # instruction-tuned completions (not chat)
)

# Substrings that suggest a well-rounded, fast chat model — scored positively.
_PREFER_KEYWORDS: tuple[str, ...] = (
    "flash",     # Gemini Flash family — fast & capable
    "turbo",     # GPT Turbo family
    "mini",      # GPT / Gemini mini — lightweight
    "small",     # Mistral Small
    "lite",      # lightweight variants
    "haiku",     # Claude Haiku — fast
    "sonnet",    # Claude Sonnet — balanced
    "latest",    # provider-maintained "latest" alias
    "fast",      # any "fast" variant
    "nano",      # any "nano" variant
)

# Cached model name resolved once per process lifetime.
_active_model: str | None = None


def _score_model(model_id: str) -> int:
    """
    Return a preference score for *model_id*.

    Negative score  → model is unsuitable for chat (will be excluded).
    Zero or above   → suitable; higher is better.
    """
    low = model_id.lower()
    for kw in _NON_CHAT_KEYWORDS:
        if kw in low:
            return -1
    score = sum(1 for kw in _PREFER_KEYWORDS if kw in low)
    return score


def _pick_model_from_list(model_ids: list[str]) -> str | None:
    """
    Choose the most suitable chat model from *model_ids*.

    Filters out non-chat models, scores the rest, and returns the highest-
    scoring one.  Returns the first available model when nothing scores
    positively, or None when *model_ids* is empty.
    """
    if not model_ids:
        return None

    scored = [(mid, _score_model(mid)) for mid in model_ids]
    chat_models = [(mid, s) for mid, s in scored if s >= 0]

    if not chat_models:
        # All models were filtered out — fall back to the raw first entry.
        return model_ids[0]

    chat_models.sort(key=lambda x: x[1], reverse=True)
    return chat_models[0][0]


async def _discover_model(client, provider: str) -> str | None:
    """
    Query the provider's models endpoint and return the best-fit model name.

    Works with both the openai-compat client (``client.models.list()``) and
    the Anthropic SDK (same interface).  Returns None if the call fails or
    no suitable model is found.
    """
    try:
        resp = await client.models.list()
        # Both openai and anthropic SDKs expose .data as a list of model objects
        model_ids: list[str] = [m.id for m in resp.data]
        if not model_ids:
            logger.warning(
                "Model discovery: provider=%r returned an empty model list",
                provider,
            )
            return None
        chosen = _pick_model_from_list(model_ids)
        logger.info(
            "Model discovery: provider=%r found %d model(s), selected %r",
            provider,
            len(model_ids),
            chosen,
        )
        return chosen
    except Exception as exc:
        logger.warning(
            "Model discovery failed for provider=%r: %s — "
            "set LLM_MODEL explicitly to skip discovery",
            provider,
            exc,
        )
        return None


async def _ensure_model_discovered(client, provider: str) -> None:
    """
    Populate *_active_model* the first time it is needed.

    Priority:
      1. ``LLM_MODEL`` env var  — user's explicit choice, never overridden.
      2. Provider's ``/models`` API  — auto-discovered at first request.
      3. Empty string  — LLM request will fail gracefully with a warning.
    """
    global _active_model
    if _active_model is not None:
        return  # already resolved

    if settings.llm_model:
        _active_model = settings.llm_model
        logger.info("Using explicitly configured model: %r", _active_model)
        return

    discovered = await _discover_model(client, provider)
    _active_model = discovered or ""
    if not _active_model:
        logger.warning(
            "Could not determine a model for provider=%r. "
            "Set LLM_MODEL in your environment to specify one.",
            provider,
        )


def _resolve_model() -> str:
    """Return the cached active model name (empty string if not yet resolved)."""
    return _active_model or ""


# ─── Lazy client — only created once when first needed ───────────────────────

_client = None
_client_provider: str | None = None   # tracks which provider the cached client serves


def _resolve_api_key() -> str:
    """
    Return the effective API key for the configured provider.
    Priority: LLM_API_KEY → OPENAI_API_KEY (legacy, openai-only fallback).
    """
    if settings.llm_api_key:
        return settings.llm_api_key
    # Legacy fallback: honour OPENAI_API_KEY for openai provider
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return settings.openai_api_key
    return ""


def _get_client():
    """
    Return a cached async LLM client for the configured provider, or None if
    the provider is disabled / key is missing.

    The client is initialised lazily on first call and cached for the lifetime
    of the process.  Settings are read from the frozen `settings` object which
    is loaded once at startup — provider changes require a process restart.

    Returns either an openai.AsyncOpenAI instance (for all OpenAI-compat
    providers) or an anthropic.AsyncAnthropic instance.
    """
    global _client, _client_provider

    if _client is not None:
        return _client

    if not app_config.ai_enabled or not settings.llm_enabled:
        return None

    provider = settings.llm_provider
    api_key = _resolve_api_key()

    if not api_key:
        logger.warning(
            "LLM disabled — no API key found for provider=%r. "
            "Set LLM_API_KEY (or OPENAI_API_KEY for openai).",
            provider,
        )
        return None

    # ── Anthropic — dedicated SDK ─────────────────────────────────────────────
    if provider == "anthropic":
        try:
            from anthropic import AsyncAnthropic  # type: ignore[import]
            _client = AsyncAnthropic(api_key=api_key)
            _client_provider = "anthropic"
            logger.info("LLM client initialised: provider=anthropic")
        except ImportError:
            logger.warning(
                "anthropic package not installed — "
                "run `pip install anthropic` to enable Anthropic support"
            )
        return _client

    # ── OpenAI-compatible providers ───────────────────────────────────────────
    if provider not in _OPENAI_COMPAT_PROVIDERS:
        logger.warning(
            "Unknown LLM_PROVIDER=%r — falling back to openai. "
            "Supported: %s",
            provider,
            ", ".join(sorted(_OPENAI_COMPAT_PROVIDERS) + ["anthropic"]),
        )
        provider = "openai"

    # Guard: "custom" provider requires an explicit base_url
    if provider == "custom" and not settings.llm_base_url:
        logger.warning(
            "LLM_PROVIDER=custom requires LLM_BASE_URL to be set — LLM disabled"
        )
        return None

    try:
        from openai import AsyncOpenAI  # type: ignore[import]

        # Resolve base_url: explicit env override > routing table > library default
        base_url: str | None = None
        if settings.llm_base_url:
            base_url = settings.llm_base_url
        elif _OPENAI_COMPAT_PROVIDERS[provider]:
            base_url = _OPENAI_COMPAT_PROVIDERS[provider]
        # base_url=None → openai library uses its own default

        _client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        _client_provider = provider
        logger.info(
            "LLM client initialised: provider=%r base_url=%r",
            provider,
            base_url or "(library default)",
        )
    except ImportError:
        logger.warning("openai package not installed — LLM responses disabled")

    return _client


# ─── Language + mode instruction builder ─────────────────────────────────────

# Human-readable names for ISO codes used in the prompt so the LLM can apply
# the right language without needing to know every 2-letter code.
_LANG_NAMES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "ar": "Arabic",
    "ru": "Russian",
    "tr": "Turkish",
    "id": "Indonesian",
}


# Well-known mixed-language blend names for the LLM prompt
_MIX_NAMES: dict[str, str] = {
    "hi": "Hinglish",
    "es": "Spanglish",
    "fr": "Franglais",
    "de": "Denglisch",
    "pt": "Portuñol",
    "ar": "Arabizi",
    "ru": "Runglish",
    "tr": "Türklish",
    "id": "Bahasa-English mix",
}


def _build_language_instruction(native_language: str, language_mode: str) -> str:
    """# UPDATED
    Return the language/style instruction block injected into the system prompt
    based on the admin-controlled language_mode and native_language settings.

    Modes
    -----
    english  → always respond in English regardless of native_language
    native   → respond entirely in native_language (no English mixing)
    mixed    → mix English with native_language (dynamic blend name per language)
    """
    from bot.i18n.languages import SUPPORTED_LANGUAGES  # lazy — avoid circular

    lang_name = _LANG_NAMES.get(native_language, native_language.upper())

    # Fallback to English for unsupported language codes
    if native_language not in SUPPORTED_LANGUAGES and native_language != "en":
        logger.warning(
            "_build_language_instruction: unsupported native_language=%r, "
            "falling back to English",
            native_language,
        )
        native_language = "en"
        language_mode = "english"
        lang_name = "English"

    if language_mode == "english":
        return (
            "Language: English\n"
            "Style: Respond entirely in English.\n"
        )
    if language_mode == "native":
        return (
            f"Language: {lang_name}\n"
            f"Style: Respond entirely in {lang_name}. Do NOT mix in English words.\n"
        )
    # mixed
    if native_language == "en":
        return (
            "Language: English\n"
            "Style: Respond in natural casual English.\n"
        )
    mix_name = _MIX_NAMES.get(native_language, f"{lang_name}-English")
    return (
        f"Language: {lang_name} + English mix ({mix_name})\n"
        f"Style: Use a natural conversational mix of English and {lang_name}, "
        f"switching between the two mid-sentence the way {mix_name} speakers do. "
        "Keep it casual and realistic.\n"
    )


# ─── Prompt template ──────────────────────────────────────────────────────────

_PROMPT_TEMPLATE = (
    "You are a real human chatting casually on Telegram.\n\n"
    "{language_instruction}"
    "Rules:\n"
    "* Keep messages short (max 1–2 lines)\n"
    "* Avoid perfect grammar\n"
    "* Sometimes use emojis 😄😅😂✨\n"
    "* Be slightly imperfect (typos allowed)\n"
    "* Do NOT sound like AI\n"
    "* Avoid repeating patterns\n"
    "* Keep conversation casual and slightly playful\n\n"
    "Personality: {persona}\n"
    "Mood: {emotional_state}\n\n"
    "Conversation:\n"
    "User: {user_message}\n\n"
    "Reply (natural, short, imperfect):"
)

# ─── AI-sounding phrases to strip ─────────────────────────────────────────────

_AI_PHRASES: list[str] = [
    "as an ai", "as a language model", "i am an ai", "i'm an ai",
    "i cannot", "i can't do that", "i must clarify", "it's important to",
    "i understand that", "certainly!", "of course!", "absolutely!",
    "i'd be happy to", "i'm here to help", "feel free to",
    "let me know if", "please note that", "i should mention",
    "i want to make sure", "in conclusion",
]

# ─── Response filter ──────────────────────────────────────────────────────────


def _filter_response(text: str) -> str | None:
    """
    Sanitise LLM output:
    1. Detect and reject AI-sounding phrases → return None to trigger fallback
    2. Enforce max 2 lines; trim excess
    3. Strip leading/trailing whitespace and quotation marks
    """
    cleaned = text.strip().strip('"').strip("'").strip()

    lower = cleaned.lower()
    for phrase in _AI_PHRASES:
        if phrase in lower:
            return None

    # Reject overly long replies (> ~200 chars)
    if len(cleaned) > 200:
        # Try to cut at sentence/clause boundary
        match = re.search(r"[.!?]\s", cleaned[:200])
        if match:
            cleaned = cleaned[: match.end()].strip()
        else:
            cleaned = cleaned[:150].rstrip()

    # Enforce max 2 lines — keep only first 2 non-empty lines
    lines = [ln for ln in cleaned.splitlines() if ln.strip()]
    if len(lines) > 2:
        cleaned = " ".join(lines[:2])

    if not cleaned:
        return None

    return cleaned


# ─── Anti-detection post-processing ──────────────────────────────────────────

_PHONETIC_SUBS: list[tuple[str, str]] = [
    ("kya", "kia"), ("nahi", "nhi"), ("hai", "h"), ("kar", "kr"),
    ("raha", "rha"), ("karo", "kro"), ("kuch", "kch"),
    ("tum", "tmm"), ("mein", "main"), ("theek", "thk"),
    ("yaar", "yar"), ("actually", "actualy"), ("because", "bcz"),
]


def _random_typo(text: str) -> str:
    """Apply one casual phonetic or character-swap typo."""
    if random.random() < 0.35:
        for original, replacement in random.sample(_PHONETIC_SUBS, len(_PHONETIC_SUBS)):
            if original in text:
                return text.replace(original, replacement, 1)
    if len(text) < 5:
        return text
    idx = random.randint(1, len(text) - 2)
    method = random.random()
    if method < 0.5:
        lst = list(text)
        lst[idx], lst[idx - 1] = lst[idx - 1], lst[idx]
        return "".join(lst)
    return text[:idx] + text[idx + 1:]


def apply_anti_detection(text: str) -> list[str]:
    """
    Randomly apply:
      • typo injection
      • message shortening (drop last clause)
      • message split into 2 parts at natural break
    Returns a list of 1–2 message strings.
    """
    # Typo injection (~25 % chance)
    if random.random() < 0.25:
        text = _random_typo(text)

    # Shortening (~15 % chance): drop text after last comma/semicolon
    if random.random() < 0.15:
        for sep in (",", ";", " -", " —"):
            idx = text.rfind(sep)
            if idx > len(text) // 2:
                text = text[:idx].strip()
                break

    # Split into 2 messages (~20 % chance) at a natural break
    if random.random() < 0.20:
        for sep in ("!", "?", ".", ","):
            idx = text.find(sep)
            if 0 < idx < len(text) - 2:
                part1 = text[: idx + 1].strip()
                part2 = text[idx + 1 :].strip()
                if part1 and part2:
                    return [part1, part2]

    return [text]


# ─── Provider-specific completion calls ──────────────────────────────────────


async def _complete_openai_compat(
    client,
    messages: list[dict],
) -> str | None:
    """Call chat.completions.create on any OpenAI-compatible client."""
    response = await client.chat.completions.create(
        model=_resolve_model(),
        messages=messages,
        max_tokens=60,
        temperature=0.9,
        timeout=8.0,
    )
    return (response.choices[0].message.content or "").strip()


async def _complete_anthropic(
    client,
    messages: list[dict],
    system_prompt: str,
) -> str | None:
    """
    Call Anthropic Messages API.
    The system prompt is passed as a top-level `system` parameter;
    the messages list must contain only user/assistant turns.
    """
    # Filter out the system message — Anthropic uses a separate `system` param
    non_system = [m for m in messages if m["role"] != "system"]
    # Anthropic requires the conversation to start with a user turn.
    # If history contains only assistant turns (or is empty), prepend a minimal
    # neutral user opener so the API contract is satisfied.
    if not non_system or non_system[0]["role"] != "user":
        logger.debug(
            "_complete_anthropic: prepending neutral user turn to satisfy "
            "Anthropic's first-message-must-be-user requirement"
        )
        non_system = [{"role": "user", "content": "..."}] + non_system

    response = await client.messages.create(
        model=_resolve_model(),
        system=system_prompt,
        messages=non_system,
        max_tokens=60,
    )
    return (response.content[0].text or "").strip() if response.content else None


# ─── Public API ───────────────────────────────────────────────────────────────


async def generate_llm_response(context: dict) -> list[str] | None:
    """
    Generate a short language-aware response using the configured LLM provider.

    context = {
        "user_message":    str,          # last message from the user (may be "")
        "persona":         str,          # e.g. "friendly", "playful"
        "tone":            str,          # "feminine" | "neutral" | "masculine"
        "history":         list[str],    # last ≤3 messages sent by the bot
        "emotional_state": str,          # "neutral" | "playful" | "shy"
        "native_language": str,          # ISO 639-1 code, e.g. "hi"
        "language_mode":   str,          # "english" | "native" | "mixed"
    }

    Returns a list[str] on success (1–2 messages after anti-detection), or
    None if the LLM is unavailable / fails / produces bad output.
    """
    client = _get_client()
    if client is None:
        return None

    # Discover / confirm model on the very first request (async, cached).
    await _ensure_model_discovered(client, _client_provider or settings.llm_provider)
    if not _resolve_model():
        logger.warning(
            "No model available for provider=%r — LLM response skipped",
            _client_provider,
        )
        return None

    user_message = context.get("user_message", "").strip()
    persona = context.get("persona", "friendly")
    emotional_state = context.get("emotional_state", "neutral")
    history: list[str] = context.get("history", [])
    native_language: str = context.get("native_language", "en")
    language_mode: str = context.get("language_mode", "english")

    language_instruction = _build_language_instruction(native_language, language_mode)

    # Build system prompt
    system_prompt = _PROMPT_TEMPLATE.format(
        language_instruction=language_instruction,
        persona=persona,
        emotional_state=emotional_state,
        user_message=user_message or "...",
    )

    # Build message list (OpenAI-style; adapted for Anthropic inside the adapter)
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for past in history[-3:]:
        messages.append({"role": "assistant", "content": past})
    if user_message:
        messages.append({"role": "user", "content": user_message})

    try:
        if _client_provider == "anthropic":
            raw = await _complete_anthropic(client, messages, system_prompt)
        else:
            raw = await _complete_openai_compat(client, messages)
    except Exception as exc:
        logger.warning("LLM request failed (provider=%r): %s", _client_provider, exc)
        return None

    if not raw:
        return None

    filtered = _filter_response(raw)
    if not filtered:
        return None

    return apply_anti_detection(filtered)

