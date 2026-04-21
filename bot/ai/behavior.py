"""
bot/ai/behavior.py — AI-only behavior controller for the fallback engine.

BehaviorController generates all responses exclusively via the configured LLM.
No hardcoded template messages are used — every chat message is AI-generated.

Tone system:
  Three tone modes per session: "feminine" | "neutral" | "masculine"
  Tone is fixed at construction time (session-consistent) and forwarded to
  the LLM prompt so responses stay in character throughout the session.
"""
from __future__ import annotations

import random

from bot.ai.personas import PERSONAS, Persona

# ─── Valid tone values ────────────────────────────────────────────────────────

_VALID_TONES = frozenset({"feminine", "neutral", "masculine"})

# ─── LLM cost-control constant ────────────────────────────────────────────────
# Hard cap on LLM calls per session to avoid runaway API spend.
# Set high enough to cover a full conversation without hitting the ceiling
# under normal usage.

MAX_LLM_CALLS_PER_SESSION: int = 50


# ─── BehaviorController ───────────────────────────────────────────────────────

class BehaviorController:
    """
    Generates responses and delays for a simulated fallback partner.

    All output is produced by the configured LLM (via llm_engine).
    If the LLM is unavailable or fails, methods return None / empty list
    rather than falling back to hardcoded templates.

    The tone parameter ("feminine" | "neutral" | "masculine") is fixed at
    construction time and does not change during the session, ensuring
    session-consistent communication style.
    """

    def __init__(
        self,
        persona_name: str | None = None,
        randomness_level: float = 0.5,  # Feature 6: 0.3 (low) → 0.7 (high)
        tone: str = "neutral",          # "feminine" | "neutral" | "masculine"
        native_language: str = "en",    # ISO 639-1 code from admin config
        language_mode: str = "english", # "english" | "native" | "mixed"
        chat_language: str = "",        # explicit LLM response language; falls back to native_language
        engagement_score: float = 0.0,  # kept for API compatibility; unused
    ) -> None:
        self._persona: Persona = (
            PERSONAS[persona_name] if persona_name and persona_name in PERSONAS
            else self._select_persona()
        )
        self._randomness_level: float = max(0.3, min(0.7, randomness_level))
        # Tone is fixed at construction — session-consistent, never changes.
        self._tone: str = tone if tone in _VALID_TONES else "neutral"
        # Language settings from admin config
        self._native_language: str = native_language or "en"
        self._language_mode: str = (
            language_mode if language_mode in ("english", "native", "mixed") else "english"
        )
        # chat_language overrides native_language for LLM responses when set
        self._chat_language: str = chat_language or self._native_language
        self._message_count: int = 0
        self._llm_call_count: int = 0
        # Short-term context: last few messages sent (for LLM history)
        self._context: list[str] = []

    # ── Persona selection ────────────────────────────────────────────────────

    def _select_persona(self) -> Persona:
        names = list(PERSONAS.keys())
        weights = [PERSONAS[n].weight for n in names]
        return PERSONAS[random.choices(names, weights=weights, k=1)[0]]

    @property
    def persona(self) -> Persona:
        return self._persona

    @property
    def tone(self) -> str:
        return self._tone

    # ── Feature 9: Global pattern metadata ──────────────────────────────────

    @property
    def current_pattern(self) -> dict:
        lo, hi = self._persona.response_speed_range
        return {
            "last_persona": self._persona.name,
            "last_delay_range": f"{lo:.1f}-{hi:.1f}",
            "last_reply_style": self._persona.typing_style,
        }

    # ── Internal LLM helper ──────────────────────────────────────────────────

    def _build_llm_context(self, user_message: str, user_history: list[str] | None = None) -> dict:
        return {
            "user_message": user_message,
            "persona": self._persona.name,
            "tone": self._tone,
            "history": list(self._context[-3:]),
            "user_history": list((user_history or [])[-5:]),
            "emotional_state": self._persona.emotional_mode,
            "native_language": self._chat_language,
            "language_mode": self._language_mode,
            "chat_language": self._chat_language,
        }

    def _record_messages(self, msgs: list[str]) -> None:
        for msg in msgs:
            self._context.append(msg)
        if len(self._context) > 10:
            self._context = self._context[-10:]

    # ── Response generation ──────────────────────────────────────────────────

    async def generate_response_async(
        self,
        user_message: str = "",
        user_history: list[str] | None = None,
        is_proactive: bool = False,
    ) -> list[str]:
        """
        Generate a response to the user's message using the LLM.

        Parameters
        ----------
        user_message : str
            The last message from the user.  May be an empty string when
            ``is_proactive`` is True.
        is_proactive : bool
            When True the bot is sending an unsolicited topic-starter (no
            recent user message).  The ``user_message`` guard is skipped so
            the LLM can produce an opener even with no user input.

        Returns a list of message strings (1–2 after anti-detection post-
        processing), or an empty list when no response should be sent
        (LLM unavailable or call cap reached).
        """
        self._message_count += 1

        # Block calls that have neither a user message nor a proactive intent,
        # and also enforce the per-session LLM call cap.
        if (not user_message and not is_proactive) or self._llm_call_count >= MAX_LLM_CALLS_PER_SESSION:
            return []

        from bot.ai.llm_engine import generate_llm_response  # lazy import

        context = self._build_llm_context(user_message, user_history=user_history)
        llm_msgs = await generate_llm_response(context)
        if llm_msgs is None:
            # Retry once on transient failure
            llm_msgs = await generate_llm_response(context)

        if llm_msgs:
            self._llm_call_count += 1
            self._record_messages(llm_msgs)
            return llm_msgs

        return []

    async def exit_message_async(self) -> str | None:
        """
        Generate a farewell message via the LLM.

        Returns a short goodbye string, or None if the LLM is unavailable.
        Language is determined by self._native_language set at construction time.
        """
        from bot.ai.llm_engine import generate_llm_response  # lazy import

        # Use an explicit farewell cue so the LLM produces a closing message.
        context = self._build_llm_context("gotta go now, ending the chat")
        msgs = await generate_llm_response(context)
        if msgs is None:
            msgs = await generate_llm_response(context)

        if msgs:
            return msgs[0]

        return None

    # ── Delay ────────────────────────────────────────────────────────────────

    def get_delay(self) -> float:
        """
        Return a randomised typing delay within the persona's speed range.

        Feature 6: The spread is scaled by randomness_level so that low values
        (0.3) produce predictably centred delays while high values (0.7) allow
        the full range with added jitter.
        """
        lo, hi = self._persona.response_speed_range
        center = (lo + hi) / 2.0
        half_spread = ((hi - lo) / 2.0) * (self._randomness_level / 0.5)
        actual_lo = max(lo, center - half_spread)
        actual_hi = min(hi, center + half_spread)
        base = random.uniform(actual_lo, actual_hi)
        jitter = random.gauss(0, 0.5 * self._randomness_level)
        return max(actual_lo, min(actual_hi, base + jitter))

    def get_burst_delay(self) -> float:
        """Very short delay between messages in a burst (0.5–2.5 s)."""
        return random.uniform(0.5, 2.5)

    # ── Exit logic ───────────────────────────────────────────────────────────

    def should_exit(self, duration_sec: float, message_count: int) -> bool:
        """Decide whether the simulated partner should end the session."""
        if duration_sec >= 480:
            return True
        if duration_sec >= 120:
            exit_prob = (duration_sec - 120) / (480 - 120)
            if random.random() < exit_prob * 0.05:
                return True
        if message_count >= random.randint(15, 30):
            return True
        return False
