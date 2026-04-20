"""
bot/utils/helpers.py — Shared utility functions.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def generate_session_id() -> str:
    """Return a unique session identifier."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def format_duration(seconds: float) -> str:
    """Format a duration in seconds to a human-readable string."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m"


def mask_user_id(user_id: int) -> str:
    """Return an anonymous display label for a user."""
    return f"Stranger#{abs(hash(user_id)) % 9999:04d}"


def sponsor_line(name: str, link: str) -> str:
    """Return a beautifully formatted HTML sponsor block.

    Returns an empty string when either *name* or *link* is blank,
    so the caller can safely append the result to any message without
    conditional checks.

    The block is designed to look elegant inside Telegram messages —
    it uses a subtle divider and an inline hyperlink so the sponsor
    notice attracts attention without feeling intrusive.

    *name* is HTML-escaped to prevent injection.  *link* is normalised
    before validation: Telegram ``@username`` handles are converted to
    ``https://t.me/username`` and bare ``t.me/…`` paths are prefixed
    with ``https://``.  Any link that still does not start with
    ``http://`` or ``https://`` after normalisation is silently
    suppressed to avoid injecting dangerous schemes.
    """
    if not name or not link:
        logger.info(
            "Sponsor footer skipped: missing value (name_present=%s, link_present=%s)",
            bool(name),
            bool(link),
        )
        return ""
    # Normalise Telegram-style links so operators can set SPONSOR_LINK
    # to "@BotName" or "t.me/BotName" without needing the full URL.
    raw_link = link
    stripped_link = raw_link.strip()
    normalized_link = stripped_link
    if normalized_link.startswith("@"):
        normalized_link = "https://t.me/" + normalized_link[1:]
    elif normalized_link.startswith("t.me/"):
        normalized_link = "https://" + normalized_link
    # Only allow safe http/https URLs — silently suppress anything else
    # to avoid injecting javascript: or other dangerous schemes.
    if not (normalized_link.startswith("https://") or normalized_link.startswith("http://")):
        logger.warning(
            "Sponsor footer skipped: invalid SPONSOR_LINK (raw=%r, normalized=%r). "
            "Link must start with http:// or https://",
            raw_link,
            normalized_link,
        )
        return ""
    if normalized_link != stripped_link:
        logger.info(
            "Sponsor link normalized for footer (stripped=%r, normalized=%r)",
            stripped_link,
            normalized_link,
        )
    if stripped_link != raw_link:
        logger.info(
            "Sponsor link whitespace trimmed for footer (raw=%r, stripped=%r)",
            raw_link,
            stripped_link,
        )
    # Escape HTML special characters in the display name so that a name
    # containing < > & " does not break the message or allow injection.
    safe_name = (
        name
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return (
        "\n\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"✨ <b>Sponsored by</b> <a href=\"{normalized_link}\">{safe_name}</a>\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄"
    )
