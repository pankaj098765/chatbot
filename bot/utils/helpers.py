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


def _escape_html(text: str) -> str:
    """Escape HTML special characters to prevent injection."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _normalize_sponsor_link(link: str) -> str | None:
    """Normalise a sponsor link and return the safe URL, or None if invalid.

    Converts Telegram ``@username`` handles to ``https://t.me/username`` and
    bare ``t.me/…`` paths to ``https://t.me/…``.  Returns ``None`` for any
    link that does not resolve to an http/https URL to block dangerous schemes.
    """
    raw_link = link
    stripped = raw_link.strip()
    normalized = stripped
    if normalized.startswith("@"):
        normalized = "https://t.me/" + normalized[1:]
    elif normalized.startswith("t.me/"):
        normalized = "https://" + normalized
    if not (normalized.startswith("https://") or normalized.startswith("http://")):
        return None
    return normalized


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
    normalized_link = _normalize_sponsor_link(link)
    # Only allow safe http/https URLs — silently suppress anything else
    # to avoid injecting javascript: or other dangerous schemes.
    if normalized_link is None:
        logger.warning(
            "Sponsor footer skipped: invalid SPONSOR_LINK (raw=%r). "
            "Link must start with http:// or https://",
            link,
        )
        return ""
    if normalized_link != link.strip():
        logger.info(
            "Sponsor link normalized for footer (raw=%r, normalized=%r)",
            link,
            normalized_link,
        )
    return (
        "\n\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"✨ <b>Sponsored by</b> <a href=\"{normalized_link}\">{_escape_html(name)}</a>\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄"
    )

