"""
backend/ingestion/url_scraper.py — extracts platform, handle, and platform-native IDs
from a social-media profile URL, and emits derived seeds so downstream scrapers run on
whatever was recovered.

Two public entrypoints:

  extract_profile_url(url) -> dict | None
      The full structured parse: platform, handle, platform_id (+ its kind), a display
      name recovered from the URL slug, and whether the URL points at a PROFILE at all.

  extract_handle(url) -> (platform, handle) | None
      The narrow legacy contract, kept byte-compatible because correlation_engine.py's
      bio_url_match signal depends on it: a bio linking to "instagram.com/johndoe" must
      normalise identically to a discovered Instagram profile's own value. It now
      returns None (instead of a junk handle) for non-profile URLs — see below.

WHY THE STRICTNESS MATTERS (this is not cosmetic):
  bio_url_match is a HARD ANCHOR in scoring_engine.py — standalone-sufficient to link
  two accounts. The previous parser reduced every one of
      facebook.com/profile.php?id=100011111111111
      facebook.com/profile.php?id=100022222222222
      facebook.com/people/Some-One/100033333333333
      facebook.com/groups/anything
  to the "handle" profile.php / people / groups. Two UNRELATED Facebook accounts both
  carrying the handle "profile.php" would then satisfy bio_url_match and link at HIGH
  confidence on a single standalone signal — exactly the red-herring class this system
  exists to refuse. Every parser below therefore classifies a URL as one of:
      profile      — a person's account page (handle and/or platform_id recovered)
      non_profile  — a post/video/group/search page: NEVER yields a handle or a seed
  and validates each handle against that platform's real charset/length rules, so a
  path segment can never be mistaken for a username.

COVERAGE (what actually enriches a case):
  instagram / twitter+x / youtube / facebook vanity / facebook /people/<slug>/<id>
      -> handle and/or name recovered, cascaded back as new seeds. Works.
  facebook.com/profile.php?id=<numeric>
      -> id recovered and recorded as evidence, but NO enrichment is possible; every
         clearnet resolution route was tested and returns nothing. See the long note
         in _parse_facebook() for the evidence and why the authenticated-browser
         workaround is deliberately not wired up.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile

# Host -> platform. Subdomains (www./m./web./mobile./old.) are stripped before lookup.
_HOSTS = {
    "instagram.com": "instagram",
    "facebook.com": "facebook",
    "fb.com": "facebook",
    "fb.me": "facebook",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "github.com": "github",
    "linkedin.com": "linkedin",
    "reddit.com": "reddit",
}

_STRIP_SUBDOMAINS = ("www.", "m.", "mobile.", "web.", "old.", "no-www.")

# Per-platform handle shape. A segment failing its platform's rule is NOT a handle.
_HANDLE_RULES = {
    # 1-30 chars, letters/digits/period/underscore.
    "instagram": re.compile(r"^[A-Za-z0-9._]{1,30}$"),
    # 1-15 chars, letters/digits/underscore only (no dots — a dotted segment is a file).
    "twitter": re.compile(r"^[A-Za-z0-9_]{1,15}$"),
    # Letters/digits/periods. "zuck" (4) is real, so no 5-char floor; ".php" is
    # excluded by _looks_like_script() before this is ever reached.
    "facebook": re.compile(r"^[A-Za-z0-9.]{2,50}$"),
    # @handles and legacy /c//user/ names.
    "youtube": re.compile(r"^[A-Za-z0-9._\-]{2,50}$"),
    "github": re.compile(r"^[A-Za-z0-9\-]{1,39}$"),
    "linkedin": re.compile(r"^[A-Za-z0-9\-_%]{2,100}$"),
    "reddit": re.compile(r"^[A-Za-z0-9_\-]{2,30}$"),
}

# Paths that are site furniture, never a person's account.
_NON_PROFILE = {
    "instagram": {"p", "reel", "reels", "tv", "explore", "direct", "accounts",
                  "about", "developer", "legal", "privacy", "challenge", "emails"},
    "facebook": {"groups", "pages", "events", "watch", "marketplace", "gaming",
                 "story.php", "photo.php", "photo", "permalink.php", "sharer",
                 "sharer.php", "dialog", "login.php", "login", "help", "search",
                 "hashtag", "media", "notes", "pg", "bookmarks", "settings"},
    "twitter": {"i", "intent", "home", "explore", "search", "notifications",
                "messages", "settings", "compose", "hashtag", "share", "login",
                "signup", "privacy", "tos", "account", "logout"},
    "youtube": {"watch", "shorts", "playlist", "results", "feed", "embed", "live",
                "gaming", "premium", "account", "hashtag", "post", "source"},
    "github": {"search", "settings", "notifications", "explore", "topics", "trending",
               "marketplace", "pulls", "issues", "orgs", "sponsors", "collections"},
    "linkedin": {"feed", "jobs", "search", "company", "school", "groups", "posts"},
    "reddit": {"r", "search", "settings", "submit", "message"},
}

# A numeric-only Facebook path IS a profile (facebook.com/100012345678901).
_NUMERIC_RE = re.compile(r"^\d{5,25}$")
# YouTube channel IDs are always UC + 22 base64url chars.
_YT_CHANNEL_RE = re.compile(r"^UC[A-Za-z0-9_\-]{22}$")


def _looks_like_script(segment: str) -> bool:
    """profile.php / story.php / index.html — a server script, never a username."""
    return bool(re.search(r"\.(php|html?|aspx?|jsp|cgi)$", segment, re.I))


def _platform_for_host(host: str) -> str | None:
    host = (host or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    for prefix in _STRIP_SUBDOMAINS:
        if host.startswith(prefix):
            host = host[len(prefix):]
            break
    return _HOSTS.get(host)


def _valid_handle(platform: str, candidate: str) -> bool:
    if not candidate or _looks_like_script(candidate):
        return False
    if candidate.lower() in _NON_PROFILE.get(platform, set()):
        return False
    rule = _HANDLE_RULES.get(platform)
    if rule and not rule.match(candidate):
        return False
    # An all-numeric segment is an ID, not a handle — callers record it as platform_id.
    return not candidate.isdigit()


def _name_from_slug(slug: str) -> str | None:
    """'John-Doe' / 'john.doe' -> 'John Doe'. Only returns a plausible human name."""
    raw = re.sub(r"[._\-+]+", " ", (slug or "").strip()).strip()
    if not raw or len(raw) < 3 or raw.isdigit():
        return None
    pretty = " ".join(w.capitalize() for w in raw.split() if w)
    try:  # lazy: name_intel is heavier and this module is imported by correlation
        from backend.analysis.name_intel import is_generic_name, is_plausible_name
        if not is_plausible_name(pretty) or is_generic_name(pretty):
            return None
    except Exception:
        if len(pretty.split()) < 2:
            return None
    return pretty


def _result(platform, kind, handle=None, platform_id=None, id_kind=None,
            name_hint=None, note="") -> dict:
    return {"platform": platform, "kind": kind, "handle": handle,
            "platform_id": platform_id, "id_kind": id_kind,
            "name_hint": name_hint, "note": note}


# --------------------------------------------------------------------------------------
# Per-platform parsers. Each takes the path segments + query dict, returns a _result().
# --------------------------------------------------------------------------------------
def _parse_facebook(segs: list[str], qs: dict) -> dict:
    if not segs:
        return _result("facebook", "non_profile", note="no path")
    head = segs[0].lower()

    # facebook.com/profile.php?id=<numeric>  — the ID is the identity; there is no handle.
    #
    # KNOWN LIMITATION — this URL form yields NO search enrichment, by necessity.
    # The numeric id is recovered and recorded as evidence (it is actually a STRONGER
    # identifier than a handle: Facebook ids are immutable, vanity handles are not), but
    # nothing downstream can turn it into a searchable name. Every clearnet route was
    # tested against a live id on 2026-09-01 and all four returned nothing:
    #   * direct HTTPS fetch of the profile page  -> HTTP 400 (Facebook serves
    #     profile.php to logged-out clients no longer; no <title>, no og: tags)
    #   * socid_extractor (socid_enrich.py)       -> no Facebook scheme exists at all
    #   * Wayback (already in the "url" tool map) -> no archived snapshot
    #   * Serper exact-match on the numeric id    -> 0 results (not indexed anywhere)
    # The only mechanism that could work is an AUTHENTICATED real browser
    # (agentic_browser/authed_browser.py's dedicated Chrome profile). That is
    # deliberately NOT wired up here: it requires logging a real Facebook account into
    # the scraper profile, which carries ToS/ban and attribution risk (see that module's
    # own docstring), and changes the evidentiary posture from anonymous public
    # collection to authenticated access. As of this writing that module's Chromium
    # runtime is not installed either, and its live_available() does not detect that.
    # If this form ever must be supported, use a dedicated burner account, never a
    # personal one, and record the authenticated capture as such in the evidence trail.
    #
    # A vanity URL (facebook.com/<handle>) or a /people/<Name-Slug>/<id> URL DOES enrich
    # normally — the handle / name slug cascade like any other seed.
    if head == "profile.php":
        fid = (qs.get("id") or [""])[0]
        if _NUMERIC_RE.match(fid):
            return _result("facebook", "profile", platform_id=fid,
                           id_kind="facebook_numeric_id", note="profile.php?id=")
        return _result("facebook", "non_profile", note="profile.php without a usable id")

    # facebook.com/people/<Name-Slug>/<numeric-id>
    if head == "people":
        name_hint = _name_from_slug(segs[1]) if len(segs) > 1 else None
        fid = next((s for s in segs[2:3] if _NUMERIC_RE.match(s)), None)
        if fid or name_hint:
            return _result("facebook", "profile", platform_id=fid,
                           id_kind="facebook_numeric_id" if fid else None,
                           name_hint=name_hint, note="/people/ vanity path")
        return _result("facebook", "non_profile", note="/people/ without id or name")

    # facebook.com/<numeric-id> is a valid profile-by-id form.
    if _NUMERIC_RE.match(head):
        return _result("facebook", "profile", platform_id=segs[0],
                       id_kind="facebook_numeric_id", note="numeric profile path")

    if head in _NON_PROFILE["facebook"] or _looks_like_script(head):
        return _result("facebook", "non_profile", note=f"reserved path '{segs[0]}'")

    if _valid_handle("facebook", segs[0]):
        return _result("facebook", "profile", handle=segs[0], note="vanity handle")
    return _result("facebook", "non_profile", note="unrecognised path")


def _parse_instagram(segs: list[str], qs: dict) -> dict:
    if not segs:
        return _result("instagram", "non_profile", note="no path")
    head = segs[0].lower()

    # instagram.com/stories/<username>/<story-id> — the username is recoverable.
    if head == "stories" and len(segs) > 1 and _valid_handle("instagram", segs[1]):
        return _result("instagram", "profile", handle=segs[1], note="from /stories/ path")

    if head in _NON_PROFILE["instagram"]:
        return _result("instagram", "non_profile", note=f"reserved path '{segs[0]}'")

    if _valid_handle("instagram", segs[0]):
        return _result("instagram", "profile", handle=segs[0], note="handle path")
    return _result("instagram", "non_profile", note="unrecognised path")


def _parse_twitter(segs: list[str], qs: dict) -> dict:
    if not segs:
        return _result("twitter", "non_profile", note="no path")
    head = segs[0].lower()

    # twitter.com/i/user/<numeric-id>
    if head == "i":
        if len(segs) >= 3 and segs[1].lower() == "user" and segs[2].isdigit():
            return _result("twitter", "profile", platform_id=segs[2],
                           id_kind="twitter_numeric_id", note="/i/user/ path")
        return _result("twitter", "non_profile", note="/i/ internal path")

    # twitter.com/intent/follow?screen_name=x  |  intent/user?user_id=123
    if head == "intent":
        screen = (qs.get("screen_name") or [""])[0]
        uid = (qs.get("user_id") or [""])[0]
        if screen and _valid_handle("twitter", screen):
            return _result("twitter", "profile", handle=screen, note="intent screen_name")
        if uid.isdigit():
            return _result("twitter", "profile", platform_id=uid,
                           id_kind="twitter_numeric_id", note="intent user_id")
        return _result("twitter", "non_profile", note="/intent/ without identifier")

    if head in _NON_PROFILE["twitter"]:
        return _result("twitter", "non_profile", note=f"reserved path '{segs[0]}'")

    if _valid_handle("twitter", segs[0]):
        return _result("twitter", "profile", handle=segs[0], note="handle path")
    return _result("twitter", "non_profile", note="unrecognised path")


def _parse_youtube(segs: list[str], qs: dict, host: str) -> dict:
    if "youtu.be" in host:
        return _result("youtube", "non_profile", note="youtu.be video link")
    if not segs:
        return _result("youtube", "non_profile", note="no path")
    head = segs[0]

    if head.startswith("@"):                       # youtube.com/@MrBeast
        handle = head[1:]
        if _valid_handle("youtube", handle):
            return _result("youtube", "profile", handle=handle, note="@handle")
        return _result("youtube", "non_profile", note="malformed @handle")

    if head.lower() == "channel":                  # youtube.com/channel/UC...
        if len(segs) > 1 and _YT_CHANNEL_RE.match(segs[1]):
            return _result("youtube", "profile", platform_id=segs[1],
                           id_kind="youtube_channel_id", note="/channel/ id")
        return _result("youtube", "non_profile", note="/channel/ without a valid UC id")

    if head.lower() in ("c", "user"):              # legacy custom / username URLs
        if len(segs) > 1 and _valid_handle("youtube", segs[1]):
            return _result("youtube", "profile", handle=segs[1], note=f"/{head}/ legacy path")
        return _result("youtube", "non_profile", note=f"/{head}/ without a valid name")

    if head.lower() in _NON_PROFILE["youtube"]:
        return _result("youtube", "non_profile", note=f"reserved path '{head}'")

    if _valid_handle("youtube", head):             # legacy bare custom URL
        return _result("youtube", "profile", handle=head, note="legacy bare custom path")
    return _result("youtube", "non_profile", note="unrecognised path")


def _parse_generic(platform: str, segs: list[str], qs: dict) -> dict:
    """github / linkedin / reddit — handle-only platforms, no ID forms to recover."""
    prefix = {"linkedin": "in", "reddit": "user"}.get(platform)
    if prefix:
        if len(segs) >= 2 and segs[0].lower() == prefix and _valid_handle(platform, segs[1]):
            return _result(platform, "profile", handle=segs[1], note=f"/{prefix}/ path")
        return _result(platform, "non_profile", note=f"not a /{prefix}/ profile path")
    if segs and _valid_handle(platform, segs[0]):
        return _result(platform, "profile", handle=segs[0], note="handle path")
    return _result(platform, "non_profile", note="unrecognised path")


def extract_profile_url(url: str) -> dict | None:
    """Structured parse of a social profile URL.

    Returns None for a non-social/unrecognised host. Otherwise a dict with:
        platform    — instagram | facebook | twitter | youtube | github | linkedin | reddit
        kind        — "profile" (a person's account) or "non_profile" (post/video/group/…)
        handle      — the username, if the URL carries one (None otherwise)
        platform_id — the platform's own stable id, if the URL carries one
        id_kind     — facebook_numeric_id | twitter_numeric_id | youtube_channel_id
        name_hint   — display name recovered from a vanity slug (e.g. /people/John-Doe/)
        note        — which rule matched, for the evidence trail
    """
    raw = (url or "").strip()
    if not raw:
        return None
    if not re.match(r"^[a-z][a-z0-9+.\-]*://", raw, re.I):
        raw = "https://" + raw          # bios/user input often omit the scheme
    try:
        parsed = urlparse(raw)
    except Exception:
        return None

    platform = _platform_for_host(parsed.netloc)
    if not platform:
        return None

    segs = [s for s in (parsed.path or "").split("/") if s]
    qs = parse_qs(parsed.query or "")

    if platform == "facebook":
        return _parse_facebook(segs, qs)
    if platform == "instagram":
        return _parse_instagram(segs, qs)
    if platform == "twitter":
        return _parse_twitter(segs, qs)
    if platform == "youtube":
        return _parse_youtube(segs, qs, (parsed.netloc or "").lower())
    return _parse_generic(platform, segs, qs)


def extract_handle(url: str) -> tuple[str, str] | None:
    """Legacy narrow contract: (platform, handle) or None.

    Kept because correlation_engine.py's bio_url_match compares a bio's link against a
    discovered profile's (platform, value) using this exact normalisation. Returns None
    whenever the URL has no real handle — including ID-only profile URLs — so a
    non-profile path can never masquerade as a username in a hard-anchor signal.
    """
    info = extract_profile_url(url)
    if info and info["kind"] == "profile" and info["handle"]:
        return info["platform"], info["handle"]
    return None


def _is_known_host(url: str) -> bool:
    return extract_profile_url(url) is not None


class URLScraper(BaseDataSource):
    name = "url_scraper"

    async def _run_live(self, url: str) -> list[RawProfile]:
        return self._build(url)

    def _run_mock(self, url: str) -> list[RawProfile]:
        return self._build(url)

    def _build(self, url: str) -> list[RawProfile]:
        url = (url or "").strip()
        info = extract_profile_url(url)

        if info is None:
            # Unknown host: keep the old best-effort "last path segment is the handle"
            # behaviour so non-social profile pages still cascade.
            parts = [p for p in url.split("/") if p]
            if len(parts) >= 2 and parts[-2].lower() not in ("www.google.com", "google.com", "search"):
                cand = parts[-1].split("?")[0].split("#")[0]
                if cand and not cand.isdigit() and not _looks_like_script(cand):
                    return [
                        make_profile("url", url, "unknown", url,
                                     metadata={"handle": cand, "platform": "unknown",
                                               "note": f"Extracted handle {cand} from URL"}),
                        make_profile("username", cand, "derived", "",
                                     metadata={"derived_from": url, "cascade": True}),
                    ]
            return []

        platform = info["platform"]
        handle, pid, name_hint = info["handle"], info["platform_id"], info["name_hint"]

        # Everything recovered from the URL goes into the evidence trail, including the
        # reason a non-profile URL produced no seed.
        meta = {
            "platform": platform,
            "url_kind": info["kind"],
            "note": info["note"],
        }
        if handle:
            meta["handle"] = handle
        if pid:
            meta["platform_id"] = pid
            meta["id_kind"] = info["id_kind"]
        if name_hint:
            meta["name_hint"] = name_hint

        out = [make_profile("url", url, platform, url, metadata=meta)]

        if info["kind"] != "profile":
            return out          # post/video/group page: recorded, but NEVER seeded

        # Derived cascade seeds — each is just a new seed for the normal
        # scrape -> correlate -> score pipeline; none of them assert a link.
        if handle:
            out.append(make_profile(
                "username", handle, "derived", "",
                metadata={"derived_from": url, "cascade": True,
                          "derived_platform": platform},
            ))
        if name_hint:
            out.append(make_profile(
                "name", name_hint, "derived", "",
                metadata={"derived_from": url, "cascade": True,
                          "derived_strategy": "url_slug_name"},
            ))
        return out
