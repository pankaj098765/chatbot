"""
bot/ai/personas.py — Persona definitions for the fallback simulated partner.

Four personas drive the BehaviorController (bot/ai/behavior.py):
  shy          — slow, short, hesitant
  friendly     — medium pace, mixed length, Hinglish
  flirty_safe  — playful, emoji-heavy, medium length
  dry_texter   — fast, very short, terse
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Persona:
    name: str
    response_speed_range: Tuple[float, float]  # (min_sec, max_sec)
    message_length: str        # "short" | "medium" | "long"
    emoji_frequency: float     # 0.0–1.0 probability of appending an emoji
    typing_style: str          # "hesitant" | "natural" | "playful" | "terse"
    hinglish_mix: bool         # occasionally inject Hinglish phrases
    typo_rate: float           # probability of a small typo per message
    weight: float = 1.0        # relative sampling weight


PERSONAS: dict[str, Persona] = {
    "shy": Persona(
        name="shy",
        response_speed_range=(6.0, 15.0),
        message_length="short",
        emoji_frequency=0.2,
        typing_style="hesitant",
        hinglish_mix=False,
        typo_rate=0.05,
        weight=1.0,
    ),
    "friendly": Persona(
        name="friendly",
        response_speed_range=(3.0, 8.0),
        message_length="medium",
        emoji_frequency=0.6,
        typing_style="natural",
        hinglish_mix=True,
        typo_rate=0.08,
        weight=2.0,
    ),
    "flirty_safe": Persona(
        name="flirty_safe",
        response_speed_range=(4.0, 10.0),
        message_length="medium",
        emoji_frequency=0.75,
        typing_style="playful",
        hinglish_mix=True,
        typo_rate=0.10,
        weight=1.5,
    ),
    "dry_texter": Persona(
        name="dry_texter",
        response_speed_range=(1.5, 5.0),
        message_length="short",
        emoji_frequency=0.05,
        typing_style="terse",
        hinglish_mix=False,
        typo_rate=0.03,
        weight=1.0,
    ),
}


def get_persona(name: str) -> Persona:
    return PERSONAS[name]
