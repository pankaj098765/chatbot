"""
bot/ai/llm_engine.py — LLM-powered multilingual response generator.

Wraps an OpenAI-compatible chat completion endpoint to produce ultra-realistic,
language-aware replies for the fallback chat engine.

Design principles:
  - Async-safe: uses openai.AsyncOpenAI under the hood
  - Non-blocking: always returns None on failure so callers fall back gracefully
  - Short output: prompt constrains LLM to 1–2 lines; response is hard-clamped
  - Anti-detection: applies random typo / shortening / message split after LLM
  - Filter: strips AI-sounding phrases and overly formal language

# UPDATED: prompt is now fully dynamic — driven by chat_language + chat_mode
  so the LLM responds in the user's chosen language and communication style.
"""
from __future__ import annotations

import logging
import random
import re

from bot.config import settings
from config.app_config import app_config

logger = logging.getLogger(__name__)

# ─── Lazy client — only created once when first needed ───────────────────────

_client = None


def _get_client():
    """Return a cached AsyncOpenAI client, or None if the key is absent."""
    global _client
    if _client is not None:
        return _client
    if not app_config.ai_enabled or not settings.openai_api_key or not settings.llm_enabled:
        return None
    try:
        from openai import AsyncOpenAI  # type: ignore[import]
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
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


def _build_language_instruction(chat_language: str, chat_mode: str) -> str:
    """# NEW
    Return the language/style instruction block that is injected into the
    system prompt based on the user's chat_language and chat_mode settings.

    Modes
    -----
    english  → always respond in English regardless of chat_language
    native   → respond entirely in chat_language (no English mixing)
    mixed    → mix English with chat_language (e.g. Hinglish for hi)
    """
    lang_name = _LANG_NAMES.get(chat_language, chat_language.upper())

    if chat_mode == "english":
        return (
            "Language: English\n"
            "Style: Respond entirely in English.\n"
        )
    if chat_mode == "native":
        return (
            f"Language: {lang_name}\n"
            f"Style: Respond entirely in {lang_name}. Do NOT mix in English words.\n"
        )
    # default: mixed
    if chat_language == "en":
        # mixed + English is just plain English
        return (
            "Language: English\n"
            "Style: Respond in natural casual English.\n"
        )
    return (
        f"Language: {lang_name} + English mix\n"
        f"Style: Use a natural mix of English and {lang_name} "
        f"(e.g. {'Hinglish' if chat_language == 'hi' else lang_name + '-English'}). "
        "Switch naturally between the two languages mid-sentence.\n"
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


# ─── Public API ───────────────────────────────────────────────────────────────


async def generate_llm_response(context: dict) -> list[str] | None:
    """
    Generate a short language-aware response using the LLM.

    context = {
        "user_message":    str,          # last message from the user (may be "")
        "persona":         str,          # e.g. "friendly", "playful"
        "tone":            str,          # "feminine" | "neutral" | "masculine"
        "history":         list[str],    # last ≤3 messages sent by the bot
        "emotional_state": str,          # "neutral" | "playful" | "shy"
        "language":        str,          # NEW — ISO 639-1 code, e.g. "hi"
        "mode":            str,          # NEW — "english" | "native" | "mixed"
    }

    Returns a list[str] on success (1–2 messages after anti-detection), or
    None if the LLM is unavailable / fails / produces bad output.
    """
    client = _get_client()
    if client is None:
        return None

    user_message = context.get("user_message", "").strip()
    persona = context.get("persona", "friendly")
    emotional_state = context.get("emotional_state", "neutral")
    history: list[str] = context.get("history", [])
    # UPDATED: pick up language/mode from context; fall back to mixed English
    chat_language: str = context.get("language", "en")
    chat_mode: str = context.get("mode", "mixed")

    # UPDATED: build dynamic language instruction
    language_instruction = _build_language_instruction(chat_language, chat_mode)

    # Build system prompt
    system_prompt = _PROMPT_TEMPLATE.format(
        language_instruction=language_instruction,
        persona=persona,
        emotional_state=emotional_state,
        user_message=user_message or "...",
    )

    # Optionally prepend recent bot history as assistant turns for richer context
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for past in history[-3:]:
        messages.append({"role": "assistant", "content": past})
    if user_message:
        messages.append({"role": "user", "content": user_message})

    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            max_tokens=60,       # hard cap — enforces short replies
            temperature=0.9,     # some creative variance
            timeout=8.0,         # fail fast; fallback handles timeout
        )
    except Exception as exc:
        logger.debug("LLM request failed: %s", exc)
        return None

    raw = (response.choices[0].message.content or "").strip()
    if not raw:
        return None

    filtered = _filter_response(raw)
    if not filtered:
        return None

    return apply_anti_detection(filtered)

