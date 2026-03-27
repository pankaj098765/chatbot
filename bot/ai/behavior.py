"""
bot/ai/behavior.py — Dynamic behavior simulation for the fallback engine.

BehaviorController selects a persona and generates varied, non-repetitive
responses with randomised delays to mimic a real chat partner.
"""
from __future__ import annotations

import random
import re

from bot.ai.personas import PERSONAS, Persona

# ─── Message pools per persona ────────────────────────────────────────────────

_MESSAGES: dict[str, list[str]] = {
    "shy": [
        "hi",
        "oh ok",
        "haha",
        "nice",
        "really?",
        "hmm",
        "i see",
        "cool i guess",
        "lol",
        "same",
        "idk",
        "kinda yeah",
        "sure",
        "maybe",
    ],
    "friendly": [
        "haha thats so cool!",
        "omg same here 😂",
        "wait really? tell me more",
        "haha yaar that's funny",
        "achi baat hai 😊",
        "that's amazing honestly",
        "I totally get you",
        "lol no way 😂",
        "same vibes fr",
        "kya scene hai bhai",
        "sounds fun!",
        "been there done that lol",
        "sahi bola yaar",
    ],
    "flirty_safe": [
        "haha ur cute for saying that 😏",
        "ooh interesting 👀",
        "lol okay mr/ms mysterious 😄",
        "sounds fun~ 🌸",
        "acha acha tell me more 😏",
        "haha okay okay I believe you 😂",
        "you seem interesting ngl 😊",
        "that's honestly adorable 🙈",
        "stop ur making me blush lol 😳",
    ],
    "dry_texter": [
        "ok",
        "lol",
        "yeah",
        "nah",
        "true",
        "idk",
        "maybe",
        "k",
        "sure",
        "whatever",
        "hm",
        "damn",
    ],
}

_HINGLISH_FILLERS = [
    "yaar ", "bhai ", "arre ", "sahi hai ", "kya baat hai ",
    "bas ", "dekh ", "sun ", "chal ", "haan ",
]

_EMOJIS = ["😂", "😊", "😏", "👀", "🙈", "😳", "🌸", "💫", "✨", "😄", "😅", "🤣"]

# Simple typo substitutions (char swap / repeat)
def _apply_typo(text: str) -> str:
    if len(text) < 3:
        return text
    idx = random.randint(1, len(text) - 2)
    char = text[idx]
    # Either swap adjacent chars or double a char
    if random.random() < 0.5:
        lst = list(text)
        lst[idx], lst[idx - 1] = lst[idx - 1], lst[idx]
        return "".join(lst)
    else:
        return text[:idx] + char + text[idx:]


class BehaviorController:
    """Generates responses and delays for a simulated fallback partner."""

    def __init__(self) -> None:
        self._persona: Persona = self._select_persona()
        self._used_messages: set[str] = set()
        self._message_count: int = 0

    # ── Persona selection ────────────────────────────────────────────────────

    def _select_persona(self) -> Persona:
        names = list(PERSONAS.keys())
        weights = [PERSONAS[n].weight for n in names]
        return PERSONAS[random.choices(names, weights=weights, k=1)[0]]

    @property
    def persona(self) -> Persona:
        return self._persona

    # ── Response generation ──────────────────────────────────────────────────

    def generate_response(self) -> str:
        pool = _MESSAGES[self._persona.name]
        # Pick a message not recently used
        available = [m for m in pool if m not in self._used_messages]
        if not available:
            self._used_messages.clear()
            available = pool

        msg = random.choice(available)
        self._used_messages.add(msg)
        self._message_count += 1

        # Hinglish prefix
        if self._persona.hinglish_mix and random.random() < 0.3:
            msg = random.choice(_HINGLISH_FILLERS) + msg

        # Typo injection
        if random.random() < self._persona.typo_rate:
            msg = _apply_typo(msg)

        # Emoji suffix
        if random.random() < self._persona.emoji_frequency:
            msg = msg + " " + random.choice(_EMOJIS)

        return msg

    # ── Delay ────────────────────────────────────────────────────────────────

    def get_delay(self) -> float:
        """Return a randomised typing delay within the persona's speed range."""
        lo, hi = self._persona.response_speed_range
        # Add slight jitter to avoid perfectly uniform distribution
        base = random.uniform(lo, hi)
        jitter = random.gauss(0, 0.5)
        return max(lo, min(hi, base + jitter))

    # ── Exit logic ───────────────────────────────────────────────────────────

    def should_exit(self, duration_sec: float, message_count: int) -> bool:
        """Decide whether the simulated partner should end the session."""
        # Hard cap at 8 minutes
        if duration_sec >= 480:
            return True
        # After 2 minutes, a random exit probability that grows over time
        if duration_sec >= 120:
            # Probability of exit increases linearly from 0 at 2 min → 1 at 8 min
            exit_prob = (duration_sec - 120) / (480 - 120)
            if random.random() < exit_prob * 0.05:  # checked per message
                return True
        # Also exit if many messages have been exchanged
        if message_count >= random.randint(15, 30):
            return True
        return False

    # ── Exit message ─────────────────────────────────────────────────────────

    def exit_message(self) -> str:
        exits = {
            "shy": ["oh i gotta go now", "bye!", "gtg sorry"],
            "friendly": ["yaar chalna hai mujhe 😅", "gotta go, was fun!", "bye bye 😊"],
            "flirty_safe": ["haha ok I really gotta go now 😏 bye~", "later! 😊"],
            "dry_texter": ["k bye", "gotta go", "cya"],
        }
        return random.choice(exits[self._persona.name])
