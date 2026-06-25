"""Identifier extractor — mines scraped profile bios for cross-platform seeds."""

import logging
import re

from backend.schemas import Identifier, IdentifierType, RawProfile

logger = logging.getLogger(__name__)

# ── Regex patterns ───────────────────────────────────────────────────

EMAIL_REGEX: re.Pattern[str] = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)

# Indian mobile numbers — optional +91 prefix, starts with 6-9
PHONE_REGEX: re.Pattern[str] = re.compile(
    r"(?:\+?91[\s-]?)?[6-9]\d{9}"
)

# Social handle mentions: "twitter: @handle", "IG @handle", "github: handle" etc.
SOCIAL_REGEX: re.Pattern[str] = re.compile(
    r"(?i)(?:twitter|x|instagram|ig|insta|github|gh|telegram|tg|reddit|tiktok|snapchat|linkedin)"
    r"\s*[:@]\s*@?([\w.-]{2,})",
)

# ── Sanity bounds ────────────────────────────────────────────────────
_EMAIL_MIN_LEN: int = 6
_EMAIL_MAX_LEN: int = 100
_USERNAME_MIN_LEN: int = 2
_USERNAME_MAX_LEN: int = 50
_MAX_IDENTIFIERS_PER_PROFILE: int = 20


def _build_text_blob(profile: RawProfile) -> str:
    """Combine relevant text fields from a profile for scanning."""
    meta = profile.metadata or {}
    parts: list[str] = [
        meta.get("bio", ""),
        meta.get("fullname", ""),
        meta.get("blog", ""),
        meta.get("location", ""),
        (
            f"twitter:{meta['twitter_username']}"
            if meta.get("twitter_username")
            else ""
        ),
    ]
    return " ".join(parts).strip()


def extract_identifiers_from_profile(
    profile: RawProfile,
    original_seed_value: str,
) -> list[Identifier]:
    """Scan a profile's text fields for additional identifiers.

    Returns a deduplicated list of Identifier objects found in the bio,
    fullname, blog, location, and twitter_username metadata fields.
    Never returns an identifier matching the original seed that produced
    this profile (avoids trivial self-loops).
    """
    text = _build_text_blob(profile)
    if not text:
        return []

    # Dedup key: (value_lower, type_value)
    seen: set[tuple[str, str]] = set()
    results: list[Identifier] = []
    seed_lower = original_seed_value.strip().lower()

    def _add(value: str, id_type: IdentifierType) -> None:
        """Add an identifier if it passes sanity checks and dedup."""
        val = value.strip()
        if not val:
            return
        key = (val.lower(), id_type.value)
        # Skip original seed
        if val.lower() == seed_lower:
            return
        # Dedup
        if key in seen:
            return
        seen.add(key)
        results.append(Identifier(type=id_type, value=val))

    # ── Emails ───────────────────────────────────────────────────────
    for match in EMAIL_REGEX.finditer(text):
        email = match.group(0).lower()
        if _EMAIL_MIN_LEN <= len(email) <= _EMAIL_MAX_LEN:
            _add(email, IdentifierType.EMAIL)

    # ── Phone numbers ────────────────────────────────────────────────
    for match in PHONE_REGEX.finditer(text):
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        normalized = digits[-10:]  # keep last 10 digits
        _add(normalized, IdentifierType.PHONE)

    # ── Social handles from bio text ─────────────────────────────────
    for match in SOCIAL_REGEX.finditer(text):
        handle = match.group(1).lstrip("@")
        if _USERNAME_MIN_LEN <= len(handle) <= _USERNAME_MAX_LEN:
            _add(handle, IdentifierType.USERNAME)

    # ── Explicit twitter_username from metadata ──────────────────────
    meta = profile.metadata or {}
    tw = meta.get("twitter_username", "")
    if tw and _USERNAME_MIN_LEN <= len(tw) <= _USERNAME_MAX_LEN:
        _add(tw, IdentifierType.USERNAME)

    # ── Emails discovered by scrapers (e.g. GitHub commit emails) ────
    for found_email in meta.get("emails_found", []):
        if isinstance(found_email, str) and _EMAIL_MIN_LEN <= len(found_email) <= _EMAIL_MAX_LEN:
            _add(found_email.lower(), IdentifierType.EMAIL)

    # ── Cap to prevent runaway extraction ────────────────────────────
    if len(results) > _MAX_IDENTIFIERS_PER_PROFILE:
        logger.warning(
            "[extractor] profile %s on %s yielded %d identifiers, capping at %d",
            profile.value,
            profile.platform,
            len(results),
            _MAX_IDENTIFIERS_PER_PROFILE,
        )
        results = results[:_MAX_IDENTIFIERS_PER_PROFILE]

    return results
