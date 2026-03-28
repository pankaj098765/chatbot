"""
bot/ai/personas.py — Persona definitions for the fallback simulated partner.

Five personas drive the BehaviorController (bot/ai/behavior.py):
  shy          — slow, short, hesitant
  friendly     — medium pace, mixed length, Hinglish
  flirty_safe  — playful, emoji-heavy, medium length
  dry_texter   — fast, very short, terse
  playful      — energetic, teasing, lots of Hinglish slang

# UPDATED
Added per-persona fields for ultra-realistic Hinglish behaviour:
  memory_inconsistency_rate — chance of "forgetting" or contradicting context
  topic_change_rate         — chance of a random non-sequitur topic jump
  question_ignore_rate      — chance of not answering the implicit question
  burst_probability         — chance of splitting reply into 2–3 quick messages
  emotional_mode            — dominant mood label for response pool selection
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class Persona:
    name: str
    response_speed_range: Tuple[float, float]  # (min_sec, max_sec)
    message_length: str             # "short" | "medium" | "long"
    emoji_frequency: float          # 0.0–1.0 probability of appending an emoji
    typing_style: str               # "hesitant" | "natural" | "playful" | "terse" | "energetic"
    hinglish_mix: bool              # occasionally inject Hinglish phrases
    typo_rate: float                # probability of a small typo per message
    memory_inconsistency_rate: float = 0.08   # chance of forgetting / contradicting
    topic_change_rate: float = 0.06           # chance of random topic jump
    question_ignore_rate: float = 0.12        # chance of silently ignoring a question
    burst_probability: float = 0.10           # chance of sending 2-3 rapid follow-up msgs
    emotional_mode: str = "neutral"           # used to pick sub-pool in behavior.py
    weight: float = 1.0                       # relative sampling weight


PERSONAS: dict[str, Persona] = {
    "shy": Persona(
        name="shy",
        response_speed_range=(7.0, 15.0),
        message_length="short",
        emoji_frequency=0.15,
        typing_style="hesitant",
        hinglish_mix=True,
        typo_rate=0.06,
        memory_inconsistency_rate=0.05,
        topic_change_rate=0.04,
        question_ignore_rate=0.20,
        burst_probability=0.05,
        emotional_mode="shy",
        weight=1.0,
    ),
    "friendly": Persona(
        name="friendly",
        response_speed_range=(3.0, 8.0),
        message_length="medium",
        emoji_frequency=0.60,
        typing_style="natural",
        hinglish_mix=True,
        typo_rate=0.10,
        memory_inconsistency_rate=0.08,
        topic_change_rate=0.08,
        question_ignore_rate=0.10,
        burst_probability=0.15,
        emotional_mode="friendly",
        weight=2.0,
    ),
    "flirty_safe": Persona(
        name="flirty_safe",
        response_speed_range=(4.0, 10.0),
        message_length="medium",
        emoji_frequency=0.75,
        typing_style="playful",
        hinglish_mix=True,
        typo_rate=0.12,
        memory_inconsistency_rate=0.10,
        topic_change_rate=0.07,
        question_ignore_rate=0.12,
        burst_probability=0.20,
        emotional_mode="flirty",
        weight=1.5,
    ),
    "dry_texter": Persona(
        name="dry_texter",
        response_speed_range=(1.5, 5.0),
        message_length="short",
        emoji_frequency=0.05,
        typing_style="terse",
        hinglish_mix=False,
        typo_rate=0.04,
        memory_inconsistency_rate=0.12,
        topic_change_rate=0.10,
        question_ignore_rate=0.25,
        burst_probability=0.05,
        emotional_mode="dry",
        weight=1.0,
    ),
    "playful": Persona(
        name="playful",
        response_speed_range=(2.0, 7.0),
        message_length="medium",
        emoji_frequency=0.65,
        typing_style="energetic",
        hinglish_mix=True,
        typo_rate=0.14,
        memory_inconsistency_rate=0.09,
        topic_change_rate=0.12,
        question_ignore_rate=0.08,
        burst_probability=0.25,
        emotional_mode="playful",
        weight=1.5,
    ),
}


def get_persona(name: str) -> Persona:
    return PERSONAS[name]
