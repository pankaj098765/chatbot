"""
bot/ai/behavior.py — Dynamic behavior simulation for the fallback engine.

BehaviorController selects a persona and generates varied, non-repetitive
responses with randomised delays to mimic a real chat partner.

# UPDATED
Feature 6:  Randomness limiter — a randomness_level (0.3–0.7) is injected at
            construction time and applied to delay spread and message variation.
Feature 9:  Global pattern breaker — the controller exposes current pattern
            metadata so fallback.py can detect and rotate away from repetition.
Ultra-human upgrade:
  - Massively expanded Hinglish message pools per persona/emotional mode
  - Realistic casual typo engine (phonetic + common chat abbreviations)
  - Memory-inconsistency: forget / contradict recent context
  - Random topic-change non-sequiturs
  - Question-ignore logic
  - Multi-message burst support (returns list of messages)
  - Richer, natural exit messages
"""
from __future__ import annotations

import random
import re

from bot.ai.personas import PERSONAS, Persona

# ─── Expanded message pools ────────────────────────────────────────────────────
# Each persona has a large, varied pool covering short / medium / longer replies.

_MESSAGES: dict[str, list[str]] = {
    "shy": [
        # very short
        "hi", "hmm", "oh", "ok", "haha", "same", "idk", "lol", "really?", "nice",
        "kinda", "maybe", "sure", "k", "hm", "ohh", "acha",
        # short Hinglish
        "haan thik hai", "pata nahi", "dekh lena", "kuch nahi bas", "acha hoga",
        "soch raha tha", "hmm yaad nahi", "thik hu", "bas yahi hai",
        # slightly longer
        "haha nahi pata yaar", "acha acha okay", "oh i see that's fine",
        "sahi lagta hai mujhe", "hmm dekhunga", "thoda weird hai tbh",
        "bas yahi tha actually", "kuch nahi ho raha aaj",
        "haan shayad hoga", "chill kar yaar sab theek hai",
        "lol nahi samjha main",
    ],
    "friendly": [
        # short
        "haha", "omg", "sahi hai!", "nice yaar", "lol what", "same here",
        # medium Hinglish
        "acha tum kaha se ho?", "kya kr rhe ho aaj?", "haha yaar that's funny ngl",
        "arrey bata na iska matlab", "omg same here 😂 bilkul same",
        "achi baat hai yaar seriously", "lol no way bhai", "kya scene hai bhai",
        "sahi bola yaar ekdum", "hahaha thik hai chill",
        "aaj ka din kaisa tha tera?", "kuch interesting ho raha hai kya?",
        "yaar bata kuch naya", "bhai tu kaafi interesting hai lol",
        "wait thoda samjha mujhe", "serious ho kya ya mazak?",
        "acha acha sun ek baat", "chal theek hai yaar",
        # slightly longer
        "yaar aaj pura din boring tha seriously kuch nahi hua",
        "haha waise mujhe bhi yahi lagta tha kabhi",
        "acha suno ek random cheez bolunga okay",
        "bhai honestly mujhe toh samajh hi nahi aaya shuru mein",
        "hahaha theek hai main maanta hu tujhe is baar",
    ],
    "flirty_safe": [
        # short teases
        "haha 😏", "ooh 👀", "really now~", "acha acha 😄", "interesting 😏",
        # medium
        "haha ur cute for saying that 😏", "ooh interesting 👀 bata aur",
        "lol okay mr/ms mysterious 😄", "sounds fun~ 🌸 tell me more",
        "acha acha tell me more 😏", "haha okay okay I believe you 😂",
        "you seem interesting ngl 😊", "that's honestly adorable 🙈",
        "stop ur making me blush lol 😳", "haha kya baat hai 😏 nice",
        "aise mat bolo yaar seriously 🙈", "haha pakka sach bol raha hai?",
        "ohhh interesting 👀 ab main curious hu", "lol theek hai theek hai 😄",
        "acha batao aur kya kya karte ho 😏",
        # slightly longer
        "haha okay okay main maan leti/leta hu tujhe 😂 this time",
        "arre yaar aise mat karo dil jeet loge 🙈",
        "lol honestly mujhe nahi pata tha tu itna interesting hoga 😊",
        "haha chal theek hai bata aur kuch 😏 curious hu",
    ],
    "dry_texter": [
        "ok", "lol", "yeah", "nah", "true", "idk", "maybe", "k", "sure",
        "whatever", "hm", "damn", "oof", "lmao", "kk", "fine", "mhm",
        "cool", "aight", "fair", "noted", "yep", "nope", "bruh",
    ],
    "playful": [
        # short bursts
        "lol what", "haha", "bhai 😂", "arre yaar", "oof", "bruh seriously",
        # medium Hinglish fun
        "lol kya kar rahe ho yaar seriously", "hahaha bhai tu toh kamal hai",
        "arre bata na kya scene hai", "yaar aaj toh pagal ho jaaunga 😂",
        "kya baat hai bhai bilkul sahi", "hahaha okay okay pakka",
        "bhai sach mein? lol no way", "arre chhod yaar kuch aur baat karte",
        "sahi hai yaar mast hai yeh", "haha dekh raha tha tujhe 😏",
        "lol theek hai chal maafi deta hu", "yaar kuch aur bhi hai life mein 😂",
        "arre nahi nahi wait wait", "hahaha okay fair enough yaar",
        "bhai yeh toh mujhe bhi pta nahi tha tbh",
        # slightly longer
        "lol yaar aaj din thoda off tha seriously kuch bhi nahi hua",
        "bhai honestly tujhse baat karke acha laga ngl",
        "hahaha arre yaar tu toh kuch bhi bol deta hai 😂",
        "okay okay seriously bata kya ho raha hai wahan",
    ],
}

# ─── Non-sequitur topic-change lines ──────────────────────────────────────────
# Injected randomly to simulate "changing topic suddenly" like real humans.

_TOPIC_CHANGERS: list[str] = [
    "btw aaj kuch khaya?",
    "arre side mein — kaunsa phone use karta hai?",
    "random question — favorite movie kya hai teri?",
    "haha waise tumhe music pasand hai?",
    "yaar ek random cheez puchni thi bas",
    "btw kahan se ho tum?",
    "acha suno kuch aur baat karte hain",
    "lol waise mausam kaisa hai wahan?",
    "arre haan ek cheez — kaunsa game khelta hai?",
    "okay change of topic — kya soch rahe ho life ke baare mein?",
    "btw koi series dekh raha hai aajkal?",
    "haha random but — pets hain ghar mein?",
]

# ─── Memory-inconsistency / contradiction lines ───────────────────────────────
# Simulates forgetting or mildly contradicting something said before.

_MEMORY_INCONSISTENCY: list[str] = [
    "wait maine kya bola tha pehle? 😅",
    "haha sorry bhai yaad nahi raha",
    "actually wait nahi nahi mera matlab kuch aur tha",
    "hmm actually ruk — pehle kya bol raha tha main lol",
    "sorry yaar thoda confused hu aaj",
    "actually haan nahi actually nahi pata 😅",
    "wait actually I take that back lol",
    "haha main toh bhool hi gaya tha 😅",
    "hmm sorry was half reading lol",
    "actually ruk — thoda alag baat thi meri",
]

# ─── Hinglish fillers ────────────────────────────────────────────────────────

_HINGLISH_FILLERS: list[str] = [
    "yaar ", "bhai ", "arre ", "sahi hai ", "kya baat hai ",
    "bas ", "dekh ", "sun ", "chal ", "haan ", "acha ", "lol ",
    "suno ", "ek second ", "btw ",
]

# ─── Per-persona emoji sets ───────────────────────────────────────────────────

_PERSONA_EMOJIS: dict[str, list[str]] = {
    "shy":        ["😊", "😅", "🙈", "😶", "👀", "😳"],
    "friendly":   ["😂", "😊", "🤣", "😄", "✨", "💫", "😅"],
    "flirty_safe":["😏", "🙈", "😳", "👀", "🌸", "💫", "😄", "😉"],
    "dry_texter": ["💀", "🙄", "😐", "😶"],
    "playful":    ["😂", "🤣", "😜", "😝", "🤪", "💥", "😎", "🔥"],
}

# ─── Realistic casual typo engine ─────────────────────────────────────────────
# Common phonetic substitutions + char swap + missing space + repeat char.

_PHONETIC_SUBS: list[tuple[str, str]] = [
    ("kya", "kia"), ("nahi", "nhi"), ("hai", "h"), ("kar", "kr"),
    ("raha", "rha"), ("karo", "kro"), ("bhai", "bhi"), ("acha", "acha"),
    ("kuch", "kch"), ("wala", "vala"), ("tum", "tmm"), ("mein", "main"),
    ("matlab", "matlb"), ("theek", "thk"), ("haan", "han"),
    ("yaar", "yar"), ("seriously", "sriously"), ("actually", "actualy"),
    ("because", "bcz"), ("with", "wid"), ("that", "tht"),
]

def _apply_typo(text: str) -> str:
    """Apply a realistic casual typo to text."""
    # 30 % chance: phonetic substitution
    if random.random() < 0.30:
        for original, replacement in random.sample(_PHONETIC_SUBS, len(_PHONETIC_SUBS)):
            if original in text:
                return text.replace(original, replacement, 1)
    if len(text) < 4:
        return text
    method = random.random()
    idx = random.randint(1, len(text) - 2)
    if method < 0.33:
        # Swap adjacent characters
        lst = list(text)
        lst[idx], lst[idx - 1] = lst[idx - 1], lst[idx]
        return "".join(lst)
    elif method < 0.66:
        # Double a character (finger slip)
        return text[:idx] + text[idx] + text[idx:]
    else:
        # Drop a character
        return text[:idx] + text[idx + 1:]


# ─── BehaviorController ───────────────────────────────────────────────────────

class BehaviorController:
    """
    Generates responses and delays for a simulated fallback partner.

    generate_response() returns a list[str] — usually one message but
    sometimes a burst of 2–3 quick follow-ups, matching how real users
    send multiple short messages in a row.
    """

    def __init__(
        self,
        persona_name: str | None = None,
        randomness_level: float = 0.5,  # Feature 6: 0.3 (low) → 0.7 (high)
    ) -> None:
        self._persona: Persona = (
            PERSONAS[persona_name] if persona_name and persona_name in PERSONAS
            else self._select_persona()
        )
        self._randomness_level: float = max(0.3, min(0.7, randomness_level))
        self._used_messages: set[str] = set()
        self._message_count: int = 0
        # Short-term context: last few messages sent (for inconsistency logic)
        self._context: list[str] = []

    # ── Persona selection ────────────────────────────────────────────────────

    def _select_persona(self) -> Persona:
        names = list(PERSONAS.keys())
        weights = [PERSONAS[n].weight for n in names]
        return PERSONAS[random.choices(names, weights=weights, k=1)[0]]

    @property
    def persona(self) -> Persona:
        return self._persona

    # ── Feature 9: Global pattern metadata ──────────────────────────────────

    @property
    def current_pattern(self) -> dict:
        lo, hi = self._persona.response_speed_range
        return {
            "last_persona": self._persona.name,
            "last_delay_range": f"{lo:.1f}-{hi:.1f}",
            "last_reply_style": self._persona.typing_style,
        }

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _pick_message(self) -> str:
        """Pick a non-recently-used message from the persona pool."""
        pool = _MESSAGES[self._persona.name]
        available = [m for m in pool if m not in self._used_messages]
        if not available:
            self._used_messages.clear()
            available = pool
        msg = random.choice(available)
        self._used_messages.add(msg)
        return msg

    def _decorate(self, msg: str) -> str:
        """Apply Hinglish filler, typo, and emoji to a base message."""
        if self._persona.hinglish_mix and random.random() < 0.30:
            msg = random.choice(_HINGLISH_FILLERS) + msg

        if random.random() < self._persona.typo_rate:
            msg = _apply_typo(msg)

        emoji_pool = _PERSONA_EMOJIS.get(self._persona.name, ["😊"])
        if random.random() < self._persona.emoji_frequency:
            msg = msg + " " + random.choice(emoji_pool)

        return msg

    # ── Response generation ──────────────────────────────────────────────────

    def generate_response(self) -> list[str]:
        """
        Return a list of 1–3 message strings.

        Behaviour:
        • memory_inconsistency_rate  → occasionally return a contradiction line
        • topic_change_rate          → occasionally inject a topic-changer
        • question_ignore_rate       → occasionally return an empty list (no reply)
        • burst_probability          → occasionally send 2–3 short messages
        """
        self._message_count += 1

        # ── Question-ignore: return nothing ──────────────────────────────────
        if random.random() < self._persona.question_ignore_rate:
            return []

        # ── Memory inconsistency ─────────────────────────────────────────────
        if self._context and random.random() < self._persona.memory_inconsistency_rate:
            return [random.choice(_MEMORY_INCONSISTENCY)]

        # ── Random topic change ──────────────────────────────────────────────
        if random.random() < self._persona.topic_change_rate:
            tc = random.choice(_TOPIC_CHANGERS)
            self._context.append(tc)
            return [tc]

        # ── Normal message(s) ────────────────────────────────────────────────
        main_msg = self._decorate(self._pick_message())
        self._context.append(main_msg)
        if len(self._context) > 10:
            self._context = self._context[-10:]

        # Burst: send a second (and rarely third) short follow-up
        messages = [main_msg]
        if random.random() < self._persona.burst_probability:
            # Second message is always short and undecorated before decoration pass
            follow_up = self._decorate(self._pick_message())
            messages.append(follow_up)
            if random.random() < 0.25:  # rare triple burst
                messages.append(self._decorate(self._pick_message()))

        return messages

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

    # ── Exit message ─────────────────────────────────────────────────────────

    def exit_message(self) -> str:
        exits: dict[str, list[str]] = {
            "shy": [
                "oh i gotta go now",
                "bye! 😊",
                "gtg sorry",
                "hmm chalna hai mujhe bye",
                "okay bye take care",
            ],
            "friendly": [
                "yaar chalna hai mujhe 😅",
                "gotta go, was fun talking!",
                "bye bye 😊 baad mein baat karte",
                "arre yaar abhi kuch kaam aa gaya gtg",
                "haha okay bye bye take care yaar",
                "chal nikal raha hu — baad mein pakka baat karte",
            ],
            "flirty_safe": [
                "haha ok I really gotta go now 😏 bye~",
                "later! 😊 was fun",
                "arre jaana padega 🙈 bye bye~",
                "lol okay gotta run — talk soon 😏",
                "battery low lol byee 🌸",
            ],
            "dry_texter": [
                "k bye",
                "gotta go",
                "cya",
                "gtg",
                "later",
                "ok bye",
            ],
            "playful": [
                "hahaha okay bhai nikal raha hu gtg 😂",
                "arre yaar baad mein baat karte seriously",
                "lol okay byee — was fun 🤣",
                "bhai phone rakhna padega gtg",
                "battery low lol byee 🔥",
                "okay chal baad me — abhi kaam hai 😜",
            ],
        }
        persona_exits = exits.get(self._persona.name, exits["friendly"])
        return random.choice(persona_exits)
