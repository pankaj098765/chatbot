"""
bot/i18n/languages.py — Supported language registry.

Defines the canonical list of languages the bot can operate in and
the default values for language-related settings.  Admin config can
restrict ``allowed_languages`` to a subset of this list.

# NEW
"""
from __future__ import annotations

# ISO 639-1 code → display name (in that language where practical)
# Covers the major world languages supported by Google Translate and similar
# platforms.  UI strings fall back to English for any language that does not
# have a dedicated translation file in bot/i18n/.
SUPPORTED_LANGUAGES: dict[str, str] = {
    # ── Tier 1: original ten ──────────────────────────────────────────────────
    "en": "English",
    "hi": "हिंदी (Hindi)",
    "es": "Español (Spanish)",
    "fr": "Français (French)",
    "de": "Deutsch (German)",
    "pt": "Português (Portuguese)",
    "ar": "العربية (Arabic)",
    "ru": "Русский (Russian)",
    "tr": "Türkçe (Turkish)",
    "id": "Bahasa Indonesia",
    # ── Tier 2: widely-spoken Asian languages ─────────────────────────────────
    "zh": "中文 (Chinese Simplified)",
    "ja": "日本語 (Japanese)",
    "ko": "한국어 (Korean)",
    "bn": "বাংলা (Bengali)",
    "ur": "اردو (Urdu)",
    "vi": "Tiếng Việt (Vietnamese)",
    "th": "ภาษาไทย (Thai)",
    "fa": "فارسی (Persian)",
    "ms": "Bahasa Melayu (Malay)",
    "ta": "தமிழ் (Tamil)",
    "te": "తెలుగు (Telugu)",
    "mr": "मराठी (Marathi)",
    "gu": "ગુજરાતી (Gujarati)",
    "pa": "ਪੰਜਾਬੀ (Punjabi)",
    "kn": "ಕನ್ನಡ (Kannada)",
    "ml": "മലയാളം (Malayalam)",
    "si": "සිංහල (Sinhala)",
    "my": "မြန်မာဘာသာ (Burmese)",
    "km": "ភាសាខ្មែរ (Khmer)",
    "lo": "ພາສາລາວ (Lao)",
    "ne": "नेपाली (Nepali)",
    # ── Tier 2: European languages ────────────────────────────────────────────
    "it": "Italiano (Italian)",
    "nl": "Nederlands (Dutch)",
    "pl": "Polski (Polish)",
    "uk": "Українська (Ukrainian)",
    "sv": "Svenska (Swedish)",
    "ro": "Română (Romanian)",
    "cs": "Čeština (Czech)",
    "el": "Ελληνικά (Greek)",
    "hu": "Magyar (Hungarian)",
    "da": "Dansk (Danish)",
    "fi": "Suomi (Finnish)",
    "sk": "Slovenčina (Slovak)",
    "bg": "Български (Bulgarian)",
    "hr": "Hrvatski (Croatian)",
    "sr": "Српски (Serbian)",
    "lt": "Lietuvių (Lithuanian)",
    "lv": "Latviešu (Latvian)",
    "et": "Eesti (Estonian)",
    "sl": "Slovenščina (Slovenian)",
    "no": "Norsk (Norwegian)",
    "ca": "Català (Catalan)",
    # ── Tier 2: African & Middle-Eastern languages ────────────────────────────
    "sw": "Kiswahili (Swahili)",
    "am": "አማርኛ (Amharic)",
    "ha": "Hausa",
    "yo": "Yorùbá (Yoruba)",
    "ig": "Igbo",
    "zu": "isiZulu (Zulu)",
    "af": "Afrikaans",
    "he": "עברית (Hebrew)",
    # ── Tier 2: Americas ──────────────────────────────────────────────────────
    "tl": "Filipino (Tagalog)",
    "jv": "Basa Jawa (Javanese)",
    "az": "Azərbaycan (Azerbaijani)",
    "kk": "Қазақ (Kazakh)",
    "uz": "O'zbek (Uzbek)",
}

# Fallback used when admin has not configured a default language
DEFAULT_LANGUAGE: str = "en"

# Fallback used when admin has not configured a default chat mode
DEFAULT_CHAT_MODE: str = "mixed"

# Valid chat modes
CHAT_MODES: dict[str, str] = {
    "english": "English only",
    "native": "Native language only",
    "mixed": "Mixed (English + native)",
}
