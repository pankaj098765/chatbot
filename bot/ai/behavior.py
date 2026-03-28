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
Tone system:
  - Three tone modes per session: "feminine" | "neutral" | "masculine"
  - Separate message pools per tone — feminine uses softer, indirect phrasing
    and never contains "bhai" / "bro"; masculine uses direct Hinglish slang.
  - Tone-specific emoji sets; tone is fixed at construction (session-consistent).
"""
from __future__ import annotations

import random

from bot.ai.personas import PERSONAS, Persona

# ─── Valid tone values ────────────────────────────────────────────────────────

_VALID_TONES = frozenset({"feminine", "neutral", "masculine"})

# ─── Tone-aware message pools ─────────────────────────────────────────────────
# Organised as _TONE_MESSAGES[tone][persona_name].
# Feminine tone:  no "bhai"/"bro"; softer, more indirect phrasing; uses "yaar".
# Neutral tone:   gender-neutral Hinglish; carries over the original pool.
# Masculine tone: direct slang; "bhai"/"bro" usage allowed.

_TONE_MESSAGES: dict[str, dict[str, list[str]]] = {

    # ── FEMININE ─────────────────────────────────────────────────────────────
    "feminine": {
        "shy": [
            # very short
            "hi", "hmm", "oh", "ok", "haha", "same", "idk", "lol", "really?", "nice",
            "kinda", "maybe", "sure", "hm", "ohh", "acha",
            # short Hinglish (no bhai/bro)
            "haan thik hai", "pata nahi", "dekh lena", "kuch nahi bas", "acha hoga",
            "soch rahi thi", "hmm yaad nahi", "thik hu", "bas yahi hai",
            # slightly longer — softer, indirect
            "haha nahi pata yaar", "acha acha okay", "oh i see that's fine",
            "sahi lagta hai mujhe", "thoda weird hai tbh",
            "bas yahi tha actually", "kuch nahi ho raha aaj",
            "haan shayad hoga", "chill karo yaar sab theek hai",
            "lol nahi samjha main",
        ],
        "friendly": [
            # short
            "haha", "omg", "sahi hai!", "nice yaar", "lol what", "same here",
            # medium Hinglish (no bhai/bro)
            "acha tum kahan se ho?", "kya kr rhe ho aaj?", "haha yaar that's funny ngl",
            "arrey bata na iska matlab", "omg same here 😄 bilkul same",
            "achi baat hai yaar seriously", "lol no way yaar",
            "sahi bola yaar ekdum", "hahaha thik hai chill",
            "aaj ka din kaisa tha tera?", "kuch interesting ho raha hai kya?",
            "yaar bata kuch naya", "tum kaafi interesting ho lol",
            "wait thoda samjha mujhe", "serious ho kya ya mazak?",
            "acha acha sun ek baat", "chal theek hai yaar",
            # slightly longer — softer phrasing
            "yaar aaj pura din boring tha seriously kuch nahi hua",
            "haha waise mujhe bhi yahi lagta tha kabhi",
            "lol tum bhi na kuch bhi bolte ho",
            "haha same yaar acha laga sun ke",
            "hahaha theek hai main maanti hu tujhe is baar",
        ],
        "flirty_safe": [
            # short teases
            "haha 😄", "ooh 👀", "really now~", "acha sachii? 😄", "interesting ✨",
            # medium — lighter, feminine tone
            "haha ur so cute for saying that 😄", "ooh interesting 👀 bata aur",
            "lol okay mysterious wala 😄", "sounds fun~ 🌸 tell me more",
            "acha acha tell me more 😄", "haha okay okay I believe you 😂",
            "you seem interesting ngl 😊", "that's honestly adorable 🙈",
            "stop ur making me blush lol 😳", "haha kya baat hai ✨ nice",
            "aise mat bolo yaar seriously 🙈", "haha sachii bol raha hai?",
            "ohhh interesting 👀 ab main curious hu", "lol theek hai theek hai 😄",
            "acha batao aur kya kya karte ho 😄",
            # slightly longer
            "haha okay okay main maan leti hu tujhe 😂 this time",
            "arre yaar aise mat karo dil jeet loge 🙈",
            "lol tum funny ho honestly nahi pata tha 😊",
            "haha chal theek hai bata aur kuch ✨ curious hu",
        ],
        "dry_texter": [
            "ok", "lol", "yeah", "nah", "true", "idk", "maybe", "k", "sure",
            "hm", "oof", "lmao", "fine", "mhm", "cool", "fair", "yep", "nope",
            "acha", "sahi", "theek hai",
        ],
        "playful": [
            # short bursts
            "lol what", "haha", "arre yaar 😄", "oof", "lol tum bhi na",
            # medium Hinglish fun (no bhai/bro)
            "lol kya kar rahe ho yaar seriously", "hahaha yaar tum toh kamal ho",
            "arre bata na kya ho raha hai", "yaar aaj toh pagal ho jaungi 😂",
            "kya baat hai yaar bilkul sahi", "hahaha okay okay pakka",
            "sachii mein? lol no way", "arre chhod yaar kuch aur baat karte",
            "sahi hai yaar mast hai yeh", "haha acha lagta hai yeh 😄",
            "lol theek hai chal", "yaar kuch aur bhi hai life mein 😂",
            "arre nahi nahi wait wait", "hahaha okay fair enough yaar",
            "lol tum funny ho yaar tbh",
            # slightly longer — lighter emotional tone
            "lol yaar aaj din thoda off tha seriously kuch bhi nahi hua",
            "haha tum se baat karke acha laga ngl 😄",
            "hahaha arre yaar tum toh kuch bhi bol dete ho 😂",
            "okay okay seriously bata kya ho raha hai wahan",
        ],
    },

    # ── NEUTRAL ───────────────────────────────────────────────────────────────
    "neutral": {
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
            "achi baat hai yaar seriously", "lol no way yaar", "kya scene hai yaar",
            "sahi bola yaar ekdum", "hahaha thik hai chill",
            "aaj ka din kaisa tha tera?", "kuch interesting ho raha hai kya?",
            "yaar bata kuch naya", "tum kaafi interesting ho lol",
            "wait thoda samjha mujhe", "serious ho kya ya mazak?",
            "acha acha sun ek baat", "chal theek hai yaar",
            # slightly longer
            "yaar aaj pura din boring tha seriously kuch nahi hua",
            "haha waise mujhe bhi yahi lagta tha kabhi",
            "acha suno ek random cheez bolna tha",
            "honestly mujhe toh samajh hi nahi aaya shuru mein",
            "hahaha theek hai main maanta hu tujhe is baar",
        ],
        "flirty_safe": [
            # short teases
            "haha 😏", "ooh 👀", "really now~", "acha acha 😄", "interesting 😏",
            # medium
            "haha ur cute for saying that 😏", "ooh interesting 👀 bata aur",
            "lol okay mysterious 😄", "sounds fun~ 🌸 tell me more",
            "acha acha tell me more 😏", "haha okay okay I believe you 😂",
            "you seem interesting ngl 😊", "that's honestly adorable 🙈",
            "stop ur making me blush lol 😳", "haha kya baat hai 😏 nice",
            "aise mat bolo yaar seriously 🙈", "haha sachii bol raha hai?",
            "ohhh interesting 👀 ab main curious hu", "lol theek hai theek hai 😄",
            "acha batao aur kya kya karte ho 😏",
            # slightly longer
            "haha okay okay main maan leta/leti hu tujhe 😂 this time",
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
            "lol what", "haha", "arre yaar", "oof", "bruh seriously",
            # medium Hinglish fun
            "lol kya kar rahe ho yaar seriously", "hahaha yaar tum toh kamal ho",
            "arre bata na kya scene hai", "yaar aaj toh pagal ho jaaunga 😂",
            "kya baat hai yaar bilkul sahi", "hahaha okay okay pakka",
            "sach mein? lol no way", "arre chhod yaar kuch aur baat karte",
            "sahi hai yaar mast hai yeh", "haha dekh raha tha tujhe 😏",
            "lol theek hai chal", "yaar kuch aur bhi hai life mein 😂",
            "arre nahi nahi wait wait", "hahaha okay fair enough yaar",
            "yeh toh mujhe bhi pta nahi tha tbh",
            # slightly longer
            "lol yaar aaj din thoda off tha seriously kuch bhi nahi hua",
            "honestly tujhse baat karke acha laga ngl",
            "hahaha arre yaar tu toh kuch bhi bol deta hai 😂",
            "okay okay seriously bata kya ho raha hai wahan",
        ],
    },

    # ── MASCULINE ─────────────────────────────────────────────────────────────
    "masculine": {
        "shy": [
            # very short
            "hi", "hmm", "oh", "ok", "haha", "same", "idk", "lol", "really?", "nice",
            "kinda", "maybe", "sure", "k", "hm", "ohh", "acha",
            # short Hinglish
            "haan thik hai", "pata nahi", "dekh lena", "kuch nahi bas", "acha hoga",
            "soch raha tha", "hmm yaad nahi", "thik hu", "bas yahi hai",
            # slightly longer
            "haha nahi pata bhai", "acha acha okay", "oh i see that's fine",
            "sahi lagta hai mujhe", "hmm dekhunga", "thoda weird hai tbh",
            "bas yahi tha actually", "kuch nahi ho raha aaj",
            "haan shayad hoga", "chill kar bhai sab theek hai",
            "lol nahi samjha main",
        ],
        "friendly": [
            # short
            "haha", "omg", "sahi hai!", "nice bhai", "lol what", "same here",
            # medium Hinglish
            "acha tum kaha se ho?", "kya kr rhe ho aaj?", "haha bhai that's funny ngl",
            "arrey bata na iska matlab", "omg same here 😂 bilkul same",
            "achi baat hai bhai seriously", "lol no way bhai", "kya scene hai bhai",
            "sahi bola bhai ekdum", "hahaha thik hai chill",
            "aaj ka din kaisa tha tera?", "kuch interesting ho raha hai kya?",
            "bhai bata kuch naya", "bro tu kaafi interesting hai lol",
            "wait thoda samjha mujhe", "serious ho kya ya mazak?",
            "acha acha sun ek baat", "chal theek hai bro",
            # slightly longer
            "bhai aaj pura din boring tha seriously kuch nahi hua",
            "haha waise mujhe bhi yahi lagta tha kabhi",
            "acha suno ek random cheez bolunga okay",
            "bhai honestly mujhe toh samajh hi nahi aaya shuru mein",
            "hahaha theek hai main maanta hu tujhe is baar",
        ],
        "flirty_safe": [
            # short teases
            "haha 😏", "ooh 👀", "really now~", "acha acha 😎", "interesting 😏",
            # medium
            "haha ur cute for saying that 😏", "ooh interesting 👀 bata aur",
            "lol okay mystery man 😎", "sounds fun bro tell me more",
            "acha acha tell me more 😏", "haha okay okay I believe you 😂",
            "you seem interesting ngl 😊", "that's honestly cool 😎",
            "stop ur making it awkward lol 😆", "haha kya baat hai 😏 nice",
            "aise mat bolo bhai seriously", "haha pakka sach bol raha hai?",
            "ohhh interesting 👀 ab main curious hu", "lol theek hai theek hai 😎",
            "acha batao aur kya kya karte ho 😏",
            # slightly longer
            "haha okay okay main maan leta hu tujhe 😂 this time",
            "arre bhai aise mat karo",
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
            "lol kya kar rahe ho bhai seriously", "hahaha bhai tu toh kamal hai",
            "arre bata na kya scene hai bhai", "yaar aaj toh pagal ho jaaunga 😂",
            "kya baat hai bhai bilkul sahi", "hahaha okay okay pakka",
            "bhai sach mein? lol no way", "arre chhod yaar kuch aur baat karte",
            "sahi hai bro mast hai yeh", "haha dekh raha tha tujhe 😏",
            "lol theek hai chal maafi deta hu", "bhai kuch aur bhi hai life mein 😂",
            "arre nahi nahi wait wait", "hahaha okay fair enough bro",
            "bhai yeh toh mujhe bhi pta nahi tha tbh",
            # slightly longer
            "lol bhai aaj din thoda off tha seriously kuch bhi nahi hua",
            "bhai honestly tujhse baat karke acha laga ngl",
            "hahaha arre bhai tu toh kuch bhi bol deta hai 😂",
            "okay okay seriously bata kya ho raha hai wahan",
        ],
    },
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
    "haha sorry yaar yaad nahi raha",
    "actually wait nahi nahi mera matlab kuch aur tha",
    "hmm actually ruk — pehle kya bol raha tha main lol",
    "sorry yaar thoda confused hu aaj",
    "actually haan nahi actually nahi pata 😅",
    "wait actually I take that back lol",
    "haha main toh bhool hi gaya tha 😅",
    "hmm sorry was half reading lol",
    "actually ruk — thoda alag baat thi meri",
]

# ─── Tone-specific Hinglish fillers ──────────────────────────────────────────
# Feminine avoids "bhai"; masculine keeps it; neutral is mixed.

_HINGLISH_FILLERS: dict[str, list[str]] = {
    "feminine": [
        "yaar ", "arre ", "sahi hai ", "kya baat hai ",
        "bas ", "dekh ", "sun ", "chal ", "haan ", "acha ", "lol ",
        "suno ", "ek second ", "btw ",
    ],
    "neutral": [
        "yaar ", "bhai ", "arre ", "sahi hai ", "kya baat hai ",
        "bas ", "dekh ", "sun ", "chal ", "haan ", "acha ", "lol ",
        "suno ", "ek second ", "btw ",
    ],
    "masculine": [
        "yaar ", "bhai ", "arre ", "bro ", "sahi hai ", "kya baat hai ",
        "bas ", "dekh ", "sun ", "chal ", "haan ", "acha ", "lol ",
        "suno ", "ek second ", "btw ",
    ],
}

# ─── Tone-specific emoji sets ─────────────────────────────────────────────────
# Tone emoji sets override per-persona sets when a tone is active.

_TONE_EMOJIS: dict[str, list[str]] = {
    "feminine":  ["😄", "😅", "😂", "🌸", "✨"],
    "neutral":   ["😊", "😂", "😄", "😅", "✨", "💫"],
    "masculine": ["😆", "😎", "😂"],
}

# ─── Per-persona emoji fallbacks (used when tone emoji pool is empty) ─────────

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
    ("raha", "rha"), ("karo", "kro"), ("acha", "achha"),
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

    The tone parameter ("feminine" | "neutral" | "masculine") is fixed at
    construction time and does not change during the session, ensuring
    session-consistent communication style.
    """

    def __init__(
        self,
        persona_name: str | None = None,
        randomness_level: float = 0.5,  # Feature 6: 0.3 (low) → 0.7 (high)
        tone: str = "neutral",          # "feminine" | "neutral" | "masculine"
    ) -> None:
        self._persona: Persona = (
            PERSONAS[persona_name] if persona_name and persona_name in PERSONAS
            else self._select_persona()
        )
        self._randomness_level: float = max(0.3, min(0.7, randomness_level))
        # Tone is fixed at construction — session-consistent, never changes.
        self._tone: str = tone if tone in _VALID_TONES else "neutral"
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

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _pick_message(self) -> str:
        """Pick a non-recently-used message from the tone+persona pool."""
        tone_pool = _TONE_MESSAGES.get(self._tone, _TONE_MESSAGES["neutral"])
        pool = tone_pool.get(self._persona.name, [])
        if not pool:
            # Fallback to neutral if persona not found in tone pool
            pool = _TONE_MESSAGES["neutral"].get(self._persona.name, ["ok"])
        available = [m for m in pool if m not in self._used_messages]
        if not available:
            self._used_messages.clear()
            available = pool
        msg = random.choice(available)
        self._used_messages.add(msg)
        return msg

    def _decorate(self, msg: str) -> str:
        """Apply tone-aware Hinglish filler, typo, and emoji to a base message."""
        if self._persona.hinglish_mix and random.random() < 0.30:
            fillers = _HINGLISH_FILLERS.get(self._tone, _HINGLISH_FILLERS["neutral"])
            msg = random.choice(fillers) + msg

        if random.random() < self._persona.typo_rate:
            msg = _apply_typo(msg)

        emoji_pool = _TONE_EMOJIS.get(self._tone) or _PERSONA_EMOJIS.get(self._persona.name, ["😊"])
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

    async def generate_response_async(
        self,
        user_message: str = "",
    ) -> list[str]:
        """
        Async response generator with hybrid LLM + template decision logic.

        Decision:
          60 % → attempt LLM (subject to cost-control guard)
          40 % → use template system directly

        Cost-control guard — LLM is skipped when:
          • self._message_count >= 10  (session no longer in early stage)
          • LLM engine returns None    (unavailable / API error)

        On LLM failure the method seamlessly falls back to the template system.

        Parameters
        ----------
        user_message:
            The most recent message sent by the human user.  Used as LLM
            context.  Pass "" when unavailable.
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

        # ── Hybrid LLM / template decision ───────────────────────────────────
        # Cost-control: LLM is only worthwhile in the early stage (first 10 msgs)
        # where engagement is highest and impression matters most.
        # self._message_count is already incremented above, so <= 10 covers msgs 1-10.
        use_llm = (
            random.random() < 0.60          # 60 % probability gate
            and self._message_count <= 10   # early session stage
            and user_message                # only when we have user context
        )

        if use_llm:
            from bot.ai.llm_engine import generate_llm_response  # lazy import

            context = {
                "user_message": user_message,
                "persona": self._persona.name,
                "tone": self._tone,
                "history": list(self._context[-3:]),
                "emotional_state": self._persona.emotional_mode,
            }
            llm_msgs = await generate_llm_response(context)
            if llm_msgs:
                for msg in llm_msgs:
                    self._context.append(msg)
                if len(self._context) > 10:
                    self._context = self._context[-10:]
                return llm_msgs
            # LLM failed — fall through to template

        # ── Template fallback ─────────────────────────────────────────────────
        main_msg = self._decorate(self._pick_message())
        self._context.append(main_msg)
        if len(self._context) > 10:
            self._context = self._context[-10:]

        messages = [main_msg]
        if random.random() < self._persona.burst_probability:
            follow_up = self._decorate(self._pick_message())
            messages.append(follow_up)
            if random.random() < 0.25:
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
