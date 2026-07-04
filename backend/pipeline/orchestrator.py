"""
backend/pipeline/orchestrator.py — runs one investigation end to end.

run_investigation(case_id) (async) and run_investigation_sync(case_id) (for
FastAPI BackgroundTasks). Flow:

  1. read case seeds
  2. for each seed, fan out the applicable scrapers in parallel (asyncio.gather,
     return_exceptions=True so one failure never kills the batch)
  2.8. bio-link cascade: URLs self-disclosed in bios that point to NOT-yet-discovered
     accounts are fed back in as new cascade seeds (see extract_bio_urls)
  3. one-level cascade: any derived username/phone seed (e.g. from a UPI, or a
     bio-link above) is run through its own tools
  4. LLM entity-extraction on free-text blobs (bios/snippets) -> extra seeds folded in
  5. dedup -> enrich (photo pHash + face embedding, structured facts) -> persist
     entities (streaming: written as soon as scraping is done); a "face" seed's
     reference photo is added as its own profile here so it's compared like any other
  6. correlate -> score -> persist clusters with LLM/template explanations
  7. ledger-log each major step; mark the case complete

DATA_MODE="mock" routes every scraper to its mock branch (dev only).
"""
from __future__ import annotations

import asyncio
import json
import uuid

from backend import config
from backend.cases.case_service import set_status
from backend.correlation.correlation_engine import correlate
from backend.database import get_db
from backend.ingestion.base_module import RawProfile, make_profile
from backend.ingestion.github_scraper import GitHubScraper
from backend.ingestion.hibp_scraper import HIBPScraper
from backend.ingestion.maigret_scraper import MaigretScraper
from backend.ingestion.mock_scraper import MockScraper
from backend.ingestion.phone_scrapers import IgnorantScraper, PhoneInfogaScraper, NumVerifyScraper
from backend.ingestion.serper_scraper import SerperScraper
from backend.ingestion.upi_module import UPIScraper
from backend.ingestion.url_scraper import URLScraper
from backend.ingestion.blackbird_scraper import BlackbirdUsernameScraper, BlackbirdEmailScraper
from backend.ingestion.socialscan_scraper import SocialscanScraper
from backend.ingestion.wayback_scraper import WaybackScraper
from backend.ingestion.reddit_scraper import RedditScraper
from backend.ingestion.telethon_scraper import TelethonScraper
from backend.ingestion.xposedornot_scraper import XposedOrNotScraper
from backend.ingestion.holehe_scraper import HoleheScraper
from backend.ingestion.sherlock_scraper import SherlockScraper
from backend.ingestion.variants import username_variants
from backend.ingestion.photo_enrich import enrich_photos, build_face_seed_profile
from backend.ingestion.profile_page_fetcher import enrich_profiles_from_page, enrich_anchors
from backend.ingestion.fact_enrich import enrich_facts
from backend.ingestion.dehashed_scraper import DehashedScraper
from backend.ingestion.leakcheck_scraper import LeakcheckScraper
from backend.correlation.correlation_engine import extract_bio_urls
from backend.ingestion.url_scraper import extract_handle
from backend.ledger.audit_ledger import log_action, save_artifact
from backend.llm.llm_client import LLMClient
from backend.pipeline.lead_reverification import reverify_leads
from backend.scoring.scoring_engine import score
from backend.analysis.reranker import rerank_and_promote

# Seed type -> scraper instances (Section 11.1). SerperScraper templates vary per seed.
def _seed_tool_map(maigret: MaigretScraper | None = None,
                   sherlock: SherlockScraper | None = None,
                   blackbird: BlackbirdUsernameScraper | None = None) -> dict:
    _maigret = maigret or MaigretScraper()
    _sherlock = sherlock or SherlockScraper()
    _blackbird = blackbird or BlackbirdUsernameScraper()
    live = {
        # DehashedScraper/LeakcheckScraper are fail-safe no-ops without their API keys
        # (return [] — see each module's docstring); wired here so the moment a key is
        # added to .env, deeper breach coverage activates with zero other changes.
        "email":    [HIBPScraper(), XposedOrNotScraper(), DehashedScraper(), LeakcheckScraper(),
                     HoleheScraper(), BlackbirdEmailScraper(), GitHubScraper(), SerperScraper('"{q}"')],
        # NumVerify (carrier/line-type/country) works with the configured key; a PLAIN
        # Serper search returns real web mentions, whereas the old site:truecaller.com
        # dork returned nothing (Truecaller blocks indexing). PhoneInfoga/ignorant stay
        # (fail-safe if their server/CLI is absent); the Facebook checker is a stub, so
        # it's dropped from the phone path. DehashedScraper/LeakcheckScraper also cover
        # phone-indexed breach records where the provider supports it.
        "phone":    [NumVerifyScraper(), PhoneInfogaScraper(), IgnorantScraper(),
                     DehashedScraper(), LeakcheckScraper(), SerperScraper('"{q}"')],
        "username": [_maigret, _sherlock, _blackbird, SocialscanScraper(), RedditScraper(), TelethonScraper(), GitHubScraper(), SerperScraper('"{q}"')],
        "upi":      [UPIScraper(), SerperScraper('"{q}"')],
        "name":     [SerperScraper('site:linkedin.com/in "{q}"'),
                     SerperScraper('site:instagram.com "{q}"'),
                     SerperScraper('site:twitter.com "{q}"'),
                     SerperScraper('site:github.com "{q}"'),
                     SerperScraper('site:reddit.com/user "{q}"'),
                     SerperScraper('site:youtube.com "{q}"'),
                     SerperScraper('site:t.me "{q}"'),
                     SerperScraper('site:facebook.com "{q}"'),
                     # Documents (resumes/CVs, official filings) — genuinely additive,
                     # not covered by any site: profile dork above.
                     SerperScraper('filetype:pdf "{q}"'),
                     SerperScraper('filetype:doc "{q}"'),
                     # Additional platforms not reachable via the generic username
                     # enumerators (Medium requires a distinct dork; Pinterest profiles
                     # aren't in Maigret/Sherlock's site lists in this deployment).
                     SerperScraper('site:medium.com "{q}"'),
                     SerperScraper('site:pinterest.com "{q}"'),
                     # Leaked-credential mentions — lower confidence (could be stale or
                     # unrelated) AND higher sensitivity (may surface PII), so every
                     # result is stamped metadata["sensitive_source"]=True for the
                     # report/UI to flag distinctly rather than presenting it like a
                     # verified profile.
                     SerperScraper('site:pastebin.com "{q}"', sensitive=True),
                     SerperScraper('"{q}"')],
        "face":     [],   # handled separately — see build_face_seed_profile() below
        "url":      [URLScraper(), WaybackScraper()],
    }
    if config.DATA_MODE == "mock":
        # development only: every seed type yields the fixed mock dataset so the full
        # pipeline (correlate/score/ledger/PDF) can run offline. UPI still parses for real.
        mock = MockScraper()
        for k in live:
            live[k] = [mock] + ([UPIScraper()] if k == "upi" else []) + ([URLScraper()] if k == "url" else [])
    return live


def _fast_username_tools() -> list:
    """Lightweight username enumerators for variant expansion — excludes the slow
    full-scan tools (Maigret, Sherlock) so checking N handle variants stays bounded."""
    return [GitHubScraper(), RedditScraper(), SocialscanScraper(),
            BlackbirdUsernameScraper()]


def _now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


async def _scrape_seed(seed_type: str, value: str, tool_map: dict) -> list[RawProfile]:
    tools = tool_map.get(seed_type, [SerperScraper('"{q}"')])
    tasks = [t.resolve(value, config.DATA_MODE) for t in tools]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    profiles: list[RawProfile] = []
    for r in results:
        if isinstance(r, list):
            profiles.extend(r)
    # Stamp the seed identifier onto each returned profile's metadata so that
    # exact_email_match / exact_phone_match / username_exact_match / exact_name_match
    # signals fire between profiles discovered from the same seed (e.g. GitHub + Holehe
    # both found via the same email address). Don't overwrite a scraper-derived value
    # (e.g. GitHub's own discovered email on a username search).
    # "name" is deliberately NOT stamped from the seed because name-based searches
    # (e.g. "Rahul Sharma") return many different people. Stamping metadata["name"]
    # on all of them causes exact_name_match to fire between every pair, incorrectly
    # clustering unrelated people. Instead we use "seed_name" for display only.
    if seed_type in {"email", "phone", "username"}:
        for p in profiles:
            if seed_type not in p.metadata:
                p.metadata[seed_type] = value
    elif seed_type == "name":
        for p in profiles:
            if "seed_name" not in p.metadata:
                p.metadata["seed_name"] = value
    return profiles


LEGITIMATE_PLATFORMS = {
    "instagram", "facebook", "twitter", "x", "linkedin", "reddit", "telegram", "tiktok",
    "youtube", "pinterest", "threads", "medium", "substack", "github", "gitlab",
    "stackoverflow", "hackernews", "leetcode", "kaggle", "discord", "patreon",
    "behance", "dribbble", "upwork", "spotify", "quora", "soundcloud",
    "twitch", "wikipedia", "gravatar", "about.me", "npm", "pypi", "dockerhub",
    "keybase", "linktree", "snapchat", "tumblr", "vimeo", "flickr", "dev.to",
    "goodreads", "bitbucket", "codepen", "replit", "huggingface", "mastodon",
    "bluesky", "fiverr", "tinder", "bumble", "okcupid", "hinge", "badoo",
    "roblox", "steam", "epicgames", "xbox", "playstation", "chess.com", "lichess",
    "foursquare", "yelp", "tripadvisor", "strava", "duolingo", "canva", "figma",
    "notion", "airbnb", "uber", "lyft", "zomato", "swiggy", "paytm", "phonepe",
    "google", "apple", "microsoft", "amazon", "yahoo", "bing", "duckduckgo",
    "wechat", "line", "viber", "whatsapp", "signal", "clubhouse", "onlyfans",
    "kofi", "buymeacoffee", "gumroad", "etsy", "ebay", "walmart", "target",
    "blogger", "wordpress", "wix", "squarespace", "weebly", "jimdo",
    "rutube", "vk", "ok.ru", "bilibili", "weibo", "zhihu", "douyin", "kuaishou",
    "xiaohongshu", "taobao", "jd", "pinduoduo", "icq", "skype", "slack", "zoom",
    "teams", "trello", "asana", "jira", "confluence",
}

_NOISE_HANDLES = {
    "a01", "a02", "a03", "a04", "a05", "a10", "a12", "a13", "a14", "a20", "a21", "a22", "a23", "a30", "a31", "a32", "a33", "a50", "a51", "a52", "a53", "a54", "a70", "a71", "a72", "a73",
    "ao3", "s21", "s22", "s23", "s24", "m31", "m32", "m51", "m52", "m53", "f12", "f22", "f23", "v10", "v20", "v30", "x10", "x20", "x30", "ps4", "ps5", "xbox", "ios", "mac", "win",
    "bot", "dev", "app", "web", "net", "org", "com", "www", "ind", "eng", "usa", "uk", "aus", "can", "ger", "fra", "rus", "chn", "jpn", "kor", "sgp", "are", "sau", "qat", "info", "admin", "support", "test", "demo", "user", "guest", "root",
}

def _is_valid_expansion_handle(val: str) -> bool:
    if not val:
        return False
    v = str(val).strip().lower().lstrip("@")
    if len(v) < 4 or len(v) > 40:
        return False
    if v.isdigit():
        return False
    if v in _NOISE_HANDLES:
        return False
    # Avoid expanding short alphanumeric noise patterns (e.g. letter followed by 2-3 digits like 'a03', 'b12')
    if len(v) <= 4 and v[0].isalpha() and v[1:].isdigit():
        return False
    return True


def _is_legitimate_and_target_country(p: RawProfile) -> bool:
    """Identifier-collection completeness gate. Kept for call-site compatibility.

    This used to also (1) drop any social/web profile whose stated location matched
    a hardcoded foreign-country wordlist unless an Indian location was ALSO present,
    and (2) require "rich" metadata (name/email/phone/bio>15 chars) for any platform
    not in a ~150-entry hardcoded allowlist. Measured live against a real username
    search ("torvalds"): of 182 unique profiles the enumerators (Maigret/Sherlock/
    Blackbird — each already false-positive-filtered via a control-probe run, see
    fp_filter.py) found, this filter silently discarded 136 of them (75%) — including
    the target's OWN real GitHub account, dropped for listing "Portland, OR" as its
    location. A filter that can delete the very account the investigator searched for
    is a correctness bug, not a feature; "focus on India" is a UI/analyst concern, not
    grounds to make an OSINT tool blind to most of what it found. Enumerator hits are
    already trustworthy without bio text — that's what fp_filter.py's control probe is
    for. Real noise gets handled downstream by the correlation/scoring engine, which
    only links on actual corroborating evidence.
    """
    return True


# Mirror / alias platforms: different site-list entries (from Maigret/Sherlock/Blackbird)
# that are really the SAME service and the SAME account. Enumerating a handle turns
# "steamcommunity.com/id/x" and "steam" into two profiles, then the correlation engine
# "matches" their identical photo/face and reports it as decisive evidence — an account
# matching its own mirror, which is noise, not intelligence. Canonicalising the platform
# before dedup collapses these into one account so it never becomes a bogus cluster.
_PLATFORM_ALIASES = {
    "steamcommunity": "steam",
    "steam community": "steam",
    "youtube user": "youtube",
    "youtube user2": "youtube",
    "youtube channel": "youtube",
    "hub": "docker hub",
    "dockerhub": "docker hub",
    "docker": "docker hub",
    "githubgist": "github",
    "github gist": "github",
    "gist": "github",
    "x": "twitter",
    "twitter (x)": "twitter",
    "insta": "instagram",
}


def _canonical_platform(platform: str) -> str:
    p = (platform or "").strip().lower()
    return _PLATFORM_ALIASES.get(p, p)


def _dedup(profiles: list[RawProfile]) -> list[RawProfile]:
    out: list[RawProfile] = []
    seen_social: dict[tuple[str, str], RawProfile] = {}
    seen_other: dict[tuple[str, str, str], RawProfile] = {}

    for p in profiles:
        if not _is_legitimate_and_target_country(p):
            continue
        plat = _canonical_platform(p.platform)
        val = (p.value or "").lower()

        if p.type == "social_account":
            key = (plat, val)
            if key in seen_social:
                existing = seen_social[key]
                # Merge metadata — richer data (from new source) fills gaps in existing.
                # Use {**existing, **p} so non-empty fields from p overwrite empty ones,
                # then overlay existing non-empty fields back on top.
                merged = {**p.metadata}
                for k, v in existing.metadata.items():
                    if v:  # keep existing non-empty values
                        merged[k] = v
                existing.metadata = merged
                if not existing.source_url and p.source_url:
                    existing.source_url = p.source_url
            else:
                p.platform = plat   # store the canonical name so the UI shows one entry
                seen_social[key] = p
                out.append(p)
        else:
            url = (p.source_url or "").lower().rstrip("/")
            key_other = (plat, val, url)
            if key_other in seen_other:
                existing = seen_other[key_other]
                merged = {**p.metadata}
                for k, v in existing.metadata.items():
                    if v:
                        merged[k] = v
                existing.metadata = merged
            else:
                seen_other[key_other] = p
                out.append(p)
    return out


async def run_investigation(case_id: str) -> dict:
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return {"status": "error", "reason": "case not found"}

    seeds = json.loads(row["seeds_json"] or "[]")
    country_filter = dict(row).get("country_filter", "ALL") or "ALL"

    # Capture the ORIGINAL identifier value(s) the investigator actually typed, BEFORE
    # variant expansion. A profile whose handle EXACTLY equals one of these is the literal
    # answer to the search ("show me ash29_03") and must surface at the top of results even
    # when it correlates with nothing else — otherwise it sinks into "not linked" while
    # variant-derived accounts that happen to cross-link get ranked above it. Exact string
    # equality only (case/space-insensitive): "ash29_03" matches "ash29_03", NOT the
    # variant "ash2903" — so this never re-introduces the substring false-positive merge.
    original_seed_values = {
        s["value"].strip().lower()
        for s in seeds
        if isinstance(s.get("value"), str) and s["value"].strip()
        and s.get("type") in ("username", "name", "email", "phone", "upi")
    }

    # 1. Username Permutation Engine & Auto-Correction
    expanded_seeds = []
    for s in seeds:
        # If user typed a full name (with spaces) into a username seed, auto-correct to name!
        if s.get("type") == "username" and isinstance(s.get("value"), str) and " " in s["value"].strip():
            s["type"] = "name"
        # Symmetric, and the more common failure: the seed-type picker used to default to
        # "name", so a plain single-token handle typed without switching the dropdown
        # (e.g. "torvalds", "ash29_03") was routed through ONLY the name path — a few
        # site:linkedin/instagram/twitter Google-dork queries — which find ~nothing for a
        # non-name string and complete in ~1s with zero results. That reads as "the
        # investigation didn't run." A real personal NAME is multi-token (first + last);
        # a single token with no space is almost always a username/handle, and username
        # enumeration (Maigret/Sherlock/Blackbird) is exactly the exact-match-first path
        # such input needs. Multi-token values stay on the name path.
        elif (s.get("type") == "name" and isinstance(s.get("value"), str)
              and s["value"].strip() and " " not in s["value"].strip()):
            s["type"] = "username"
        expanded_seeds.append(s)
        # Only generate username permutations for actual username seeds (no spaces)
        if s.get("type") == "username" and isinstance(s.get("value"), str) and " " not in s["value"].strip():
            val = s["value"].lower().strip()
            parts = [p for p in val.replace(".", " ").replace("_", " ").split() if p]
            if len(parts) >= 2:
                first, last = parts[0], parts[-1]
                perms = [
                    f"{first}{last}", f"{first}_{last}", f"{first}.{last}",
                    f"{first[0]}{last}", f"{first}{last[0]}", "".join(parts)
                ]
                for p in set(perms):
                    if p != val:
                        expanded_seeds.append({"type": "username", "value": p})
    seeds = expanded_seeds

    set_status(case_id, "running")

    # idempotent re-runs: clear prior findings (ledger stays append-only by design)
    conn = get_db()
    try:
        conn.execute("DELETE FROM entities WHERE case_id = ?", (case_id,))
        conn.execute("DELETE FROM clusters WHERE case_id = ?", (case_id,))
        conn.commit()
    finally:
        conn.close()

    log_action(case_id, "investigation_started", {"seeds": seeds}, None, "system")

    # Keep explicit references to the FP-filtered username scrapers so we can
    # read their false-positive filter info after each run and write audit-ledger entries.
    _maigret = MaigretScraper()
    _sherlock = SherlockScraper()
    _blackbird = BlackbirdUsernameScraper()
    tool_map = _seed_tool_map(_maigret, _sherlock, _blackbird)
    all_profiles: list[RawProfile] = []

    # 1+2: primary fan-out per seed
    for seed in seeds:
        ps = await _scrape_seed(seed.get("type"), seed.get("value"), tool_map)
        log_action(case_id, f"scrape:{seed.get('type')}",
                   {"value": seed.get("value")}, {"found": len(ps)}, "system")
        all_profiles.extend(ps)
        # Log false-positive filter results for username seeds (maigret + sherlock + blackbird).
        # fp_filter.py runs both real + control in parallel and caches results 6 h.
        if seed.get("type") == "username" and config.DATA_MODE == "live":
            for inst in (_maigret, _sherlock, _blackbird):
                fp = getattr(inst, "last_fp_info", None)
                if fp:
                    log_action(
                        case_id, "false_positive_filter",
                        {"tool": fp.get("tool"), "control_username": fp.get("control_username")},
                        {"excluded_sites": fp.get("excluded_sites", [])[:30],
                         "removed": fp.get("removed", 0),
                         "cache_hit": fp.get("cache_hit")},
                        "system",
                    )

    # 2.5: username-variant expansion (live only). The same person uses different
    # handles across platforms (j.shankar / jshankar / shankarj); generate variants
    # of each username seed and re-run the FAST enumerators on them to widen recall.
    if config.DATA_MODE == "live":
        searched = {(s.get("type"), str(s.get("value")).lower()) for s in seeds}
        variant_set: list[str] = []
        for s in seeds:
            if s.get("type") != "username" or not s.get("value"):
                continue
            for v in username_variants(s["value"], max_n=5):
                if _is_valid_expansion_handle(v) and ("username", v.lower()) not in searched and v not in variant_set:
                    variant_set.append(v)
        variant_set = variant_set[:8]  # global cap so expansion can't explode
        if variant_set:
            fast_tools = _fast_username_tools()

            async def _scrape_variant(v: str) -> list[RawProfile]:
                res = await asyncio.gather(*[t.resolve(v, "live") for t in fast_tools],
                                           return_exceptions=True)
                out: list[RawProfile] = []
                for r in res:
                    if isinstance(r, list):
                        for p in r:
                            p.metadata["found_via_variant"] = v
                            if "username" not in p.metadata:
                                p.metadata["username"] = v
                            out.append(p)
                return out

            var_results = await asyncio.gather(
                *[_scrape_variant(v) for v in variant_set], return_exceptions=True)
            found = 0
            for r in var_results:
                if isinstance(r, list):
                    all_profiles.extend(r)
                    found += len(r)
            log_action(case_id, "variant_expansion",
                       {"variants": variant_set}, {"found": found}, "system")

    # 2.8: bio-link cascade — a bio/description self-discloses a URL to an account we
    # have NOT already discovered (e.g. a GitHub bio linking a personal Twitter). Feed
    # any new handle back in as a "derived"+cascade profile, reusing exactly the same
    # one-level-cascade mechanism the loop below already applies to UPI-derived seeds
    # — no new cascade machinery needed, this just seeds it with more candidates.
    # (Bio URLs that DO match an already-discovered profile are handled separately by
    # correlation_engine.py's bio_url_match signal — that's corroboration, this is
    # finding NEW accounts.)
    existing_handles = {p.value.lower() for p in all_profiles if p.value}
    bio_link_count = 0
    for p in list(all_profiles):
        text = " ".join(str((p.metadata or {}).get(k) or "") for k in ("bio", "snippet"))
        if not text:
            continue
        for url in extract_bio_urls(text):
            found = extract_handle(url)
            if not found:
                continue
            _, handle = found
            if not _is_valid_expansion_handle(handle) or handle.lower() in existing_handles:
                continue
            existing_handles.add(handle.lower())
            all_profiles.append(make_profile("username", handle, "derived", url,
                                metadata={"derived_from_bio": p.value, "cascade": True}))
            bio_link_count += 1
            if bio_link_count >= 5:   # hard cap, mirrors every other expansion step
                break
        if bio_link_count >= 5:
            break
    if bio_link_count:
        log_action(case_id, "bio_link_cascade", {"found": bio_link_count}, None, "system")

    # 3: one-level cascade for derived seeds (e.g. UPI -> username/phone, bio-link above)
    derived = [p for p in all_profiles if p.platform == "derived"
               and p.metadata.get("cascade")]
    for d in derived:
        ps = await _scrape_seed(d.type, d.value, tool_map)
        log_action(case_id, f"cascade:{d.type}", {"value": d.value}, {"found": len(ps)}, "system")
        all_profiles.extend(ps)

    # 3.5: Gated 2-Hop Name Pivot (live only). When initial scraping discovers a real human name
    # on a major legitimate platform (e.g., GitHub or Instagram), pivot on that name by generating
    # targeted username variants (e.g. "Ashwin Harish" -> ashwinharish, ashwin.harish) and querying fast scrapers.
    if config.DATA_MODE == "live":
        searched_vals = {p.value.lower() for p in all_profiles if p.value}
        discovered_names: set[str] = set()
        for p in all_profiles:
            plat = (p.platform or "").lower().strip()
            if any(legit in plat for legit in LEGITIMATE_PLATFORMS):
                m = p.metadata or {}
                name_val = m.get("name") or m.get("fullname")
                if not name_val and m.get("title"):
                    t_str = str(m.get("title")).split("(@")[0].split(" - ")[0].split(" | ")[0].split(" • ")[0].strip()
                    if " " in t_str and len(t_str) >= 5 and not any(c.isdigit() for c in t_str):
                        name_val = t_str
                if name_val:
                    name_str = str(name_val).strip()
                    if (
                        len(name_str) >= 5
                        and " " in name_str
                        and name_str.lower() != (p.value or "").lower()
                        and not any(c.isdigit() for c in name_str)
                    ):
                        discovered_names.add(name_str)

        if discovered_names:
            top_name = sorted(discovered_names)[0]
            try:
                serp_res = await SerperScraper('"{q}"').resolve(top_name, "live")
                if serp_res:
                    for sp in serp_res:
                        sp.metadata["found_via_name_pivot"] = top_name
                    all_profiles.extend(serp_res)
                    log_action(case_id, "serper_name_search", {"name": top_name}, {"found": len(serp_res)}, "system")
            except Exception:
                pass

            name_variants: list[str] = []
            for n_str in sorted(discovered_names)[:2]:
                for v in username_variants(n_str, max_n=4):
                    if _is_valid_expansion_handle(v) and v.lower() not in searched_vals and v not in name_variants:
                        name_variants.append(v)
            name_variants = name_variants[:6]
            if name_variants:
                fast_tools = _fast_username_tools()

                async def _scrape_name_variant(v: str) -> list[RawProfile]:
                    res = await asyncio.gather(*[t.resolve(v, "live") for t in fast_tools],
                                               return_exceptions=True)
                    out: list[RawProfile] = []
                    for r in res:
                        if isinstance(r, list):
                            for p in r:
                                p.metadata["found_via_name_pivot"] = v
                                if "username" not in p.metadata:
                                    p.metadata["username"] = v
                                out.append(p)
                    return out

                name_results = await asyncio.gather(
                    *[_scrape_name_variant(v) for v in name_variants], return_exceptions=True)
                found_name_pivot = 0
                for r in name_results:
                    if isinstance(r, list):
                        all_profiles.extend(r)
                        found_name_pivot += len(r)
                log_action(case_id, "name_pivot_expansion",
                           {"discovered_names": list(discovered_names)[:2], "variants": name_variants},
                           {"found": found_name_pivot}, "system")


    # Archive check on discovered profile URLs (Wayback ONLY). We deliberately do
    # NOT re-run the URL parser on every discovered URL: it just re-extracts the
    # same handle we already have, flooding the case with redundant url/derived
    # entities. Capped so a 150-account run doesn't fire 150 archive.org calls.
    # Skip web_mention profiles (Serper results) — those are live public pages that
    # don't need an archival check; only social_account URLs are worth checking for
    # deleted-but-archived profiles.
    wb = WaybackScraper()
    seen_account_urls = {p.source_url for p in all_profiles
                         if p.source_url and p.source_url.startswith("http")
                         and p.type != "web_mention"}
    urls = list(seen_account_urls)[:20]
    if urls:
        async def _archive(url):
            return await wb.resolve(url, config.DATA_MODE)
        arch_results = await asyncio.gather(*[_archive(u) for u in urls], return_exceptions=True)
        found = 0
        for res in arch_results:
            if isinstance(res, list):
                all_profiles.extend(res)
                found += len(res)
        log_action(case_id, "archive_check", {"urls": len(urls)}, {"found": found}, "system")

    # 3.8: Apply country / legitimate platform filter (focus on IND) BEFORE extraction!
    # This guarantees we only extract keywords/options from legitimate Indian records,
    # and drops foreign/fake websites before LLM entity extraction ever runs.
    all_profiles = [p for p in all_profiles if _is_legitimate_and_target_country(p)]

    # 4: LLM entity-extraction over free-text blobs -> extra username/email seeds
    llm = LLMClient()
    blobs = []
    for p in all_profiles:
        for k in ("bio", "snippet"):
            v = p.metadata.get(k)
            if v and isinstance(v, str) and len(v) > 10:
                blobs.append(v)
    extracted_seeds = []
    
    # Run LLM extractions in parallel
    async def _extract(b):
        # LLMClient is synchronous, run in thread
        return await asyncio.to_thread(llm.extract_entities, b)
        
    if blobs:
        # Cap at 6 bios: entity-extraction here competes with fact-enrichment, per-cluster
        # explanations and reranking for the same LLM per-minute budget (see llm_client.py's
        # fast-degrade rationale). extract_entities has a deterministic regex fallback, so a
        # smaller cap costs little recall and keeps the provider from saturating.
        extract_tasks = [_extract(b) for b in blobs[:6]]
        extract_results = await asyncio.gather(*extract_tasks, return_exceptions=True)
        for res in extract_results:
            if isinstance(res, list):
                for ent in res:
                    if ent.get("type") == "email" and ent.get("value"):
                        extracted_seeds.append(ent)
                    elif ent.get("type") == "username" and ent.get("value"):
                        if _is_valid_expansion_handle(str(ent.get("value"))):
                            extracted_seeds.append(ent)
                        
    if extracted_seeds:
        log_action(case_id, "llm_entity_extraction", {"blobs": len(blobs)},
                   {"new_seeds": len(extracted_seeds)}, "system")

    # bio-link expansion: run scrapers on NEW identifiers self-disclosed in bios,
    # skipping ones we've already searched. Bounded to avoid runaway expansion.
    seen_seeds = {(s.get("type"), str(s.get("value")).lower()) for s in seeds}
    seen_seeds |= {(d.type, (d.value or "").lower()) for d in derived}
    
    tasks_expand = []
    expansions = 0
    for ent in extracted_seeds:
        if ent.get("type") == "username" and not _is_valid_expansion_handle(str(ent.get("value"))):
            continue
        key = (ent["type"], str(ent["value"]).lower())
        if key in seen_seeds:
            continue
        seen_seeds.add(key)
        expansions += 1
        if expansions > 5:            # hard cap (Section: max iterations)
            break
            
        async def _run_expand(e):
            res = await _scrape_seed(e["type"], e["value"], tool_map)
            log_action(case_id, f"expand:{e['type']}", {"value": e["value"]},
                       {"found": len(res)}, "system")
            return res
            
        tasks_expand.append(_run_expand(ent))
        
    if tasks_expand:
        expand_results = await asyncio.gather(*tasks_expand, return_exceptions=True)
        for res in expand_results:
            if isinstance(res, list):
                all_profiles.extend(res)

    # 5: dedup, then two enrichment passes (live only):
    #    5a. og:image / og:description — fetch profile pages for accounts where
    #        the enumerator (Maigret, Sherlock) returned a URL but no photo or bio.
    #        This is the primary mechanism for getting avatars; most maigret/sherlock
    #        site definitions have no field-extraction patterns (see maigret_scraper.py).
    #    5b. pHash — compute perceptual hashes on any photo_url now present so the
    #        profile_photo_phash signal can match the same face across platforms.
    profiles = _dedup(all_profiles)
    if str(country_filter).upper() == "INDIA":
        from backend.ingestion.country_filter import filter_profiles_by_country
        before_len = len(profiles)
        profiles = filter_profiles_by_country(profiles, "INDIA")
        log_action(case_id, "country_filter_applied", {"before": before_len, "filter": "INDIA"}, {"after": len(profiles)}, "system")

    # Flag the exact query-match accounts NOW (before enrichment), so the anchor pass can
    # target them. These are the literal answer to the search; the whole case is resolved
    # against them. Exact string equality only (never the substring/variant merge).
    if original_seed_values:
        for p in profiles:
            v = str(p.value or "").strip().lower()
            u = str((p.metadata or {}).get("username") or "").strip().lower()
            if (v and v in original_seed_values) or (u and u in original_seed_values):
                p.metadata["exact_seed_match"] = True

    if config.DATA_MODE == "live":
        # 5.0: ANCHOR pass FIRST — deep-enrich the exact-match accounts (real name,
        # location, photo, bio). Running before the generic passes means the anchor's
        # recovered photo is present when enrich_photos computes face embeddings, and its
        # name/location are present when correlate() links every other account against it.
        try:
            anchored = await enrich_anchors(profiles)
            log_action(case_id, "anchor_enrichment",
                       {"anchors": sum(1 for p in profiles if p.metadata.get('exact_seed_match'))},
                       {"anchors_with_identity": anchored}, "system")
        except Exception:
            pass
        try:
            enriched = await enrich_profiles_from_page(profiles)
            log_action(case_id, "page_enrichment", {"candidates": len(profiles)},
                       {"profiles_enriched": enriched}, "system")
        except Exception:
            pass
        try:
            hashed = await enrich_photos(profiles)
            log_action(case_id, "photo_enrichment", {"candidates": len(profiles)},
                       {"photos_hashed": hashed}, "system")
        except Exception:  # fail-safe: photo hashing must never stop a run
            pass
        try:
            facts = await enrich_facts(profiles)
            log_action(case_id, "fact_enrichment", {"candidates": len(profiles)},
                       {"profiles_with_facts": facts}, "system")
        except Exception:  # fail-safe: fact extraction must never stop a run
            pass

        # 5c: face seed (investigator-supplied reference photo). Added as its own
        # RawProfile so the existing pairwise correlate()/score() pipeline compares it
        # against every discovered profile's face_embedding with zero special-casing —
        # same pattern every other seed-derived profile already uses.
        for s in seeds:
            if s.get("type") == "face" and s.get("value"):
                try:
                    face_profile = await build_face_seed_profile(s["value"])
                except Exception:
                    face_profile = None
                if face_profile:
                    profiles.append(face_profile)
                    log_action(case_id, "face_seed_processed", {"value": s["value"]},
                               {"embedding_extracted": True}, "system")
                else:
                    log_action(case_id, "face_seed_processed", {"value": s["value"]},
                               {"embedding_extracted": False,
                                "reason": "fetch failed or no face detected"}, "system")

        def _has_content_metadata(p: RawProfile) -> bool:
            if p.type not in ("social_account", "username"):
                return True
            # A confirmed platform+handle hit (Maigret/Sherlock/Blackbird/Socialscan) is
            # substantive on its own — that confirmation IS the OSINT finding, whether or
            # not the tool also scraped a bio. "site_name" used to be blocklisted here,
            # but it's Sherlock's ONLY metadata field (see sherlock_scraper.py), so this
            # filter was silently deleting 100% of every Sherlock result (86/86 on a live
            # "torvalds" test) — one of the three enumerator backbones, gone. Only drop a
            # profile when it lacks even a platform/value pair (a bare, unconfirmed stub).
            if p.platform and p.value:
                return True
            meta = getattr(p, "metadata", {}) or {}
            boilerplate = {"tags", "all_ids", "source", "registered", "service", "derived_from", "cascade", "username", "id", "url", "note", "raw_line", "error"}
            for k, v in meta.items():
                if k not in boilerplate and v not in (None, "", [], {}, "null", "None", 0):
                    return True
            return False

        before_meta = len(profiles)
        profiles = [p for p in profiles if _has_content_metadata(p)]
        if len(profiles) != before_meta:
            log_action(case_id, "empty_metadata_filter", {"before": before_meta}, {"after": len(profiles)}, "system")
    # Flag the profile(s) that EXACTLY match what the investigator searched for, so the
    # UI can pin them to the top regardless of whether they linked to anything. Match on
    # the account value OR its stored username field (some scrapers put the handle there).
    if original_seed_values:
        for p in profiles:
            v = str(p.value or "").strip().lower()
            u = str((p.metadata or {}).get("username") or "").strip().lower()
            if (v and v in original_seed_values) or (u and u in original_seed_values):
                p.metadata["exact_seed_match"] = True

    idx_to_eid: dict[int, str] = {}
    conn = get_db()
    try:
        for i, p in enumerate(profiles):
            eid = uuid.uuid4().hex
            idx_to_eid[i] = eid
            conn.execute(
                """INSERT INTO entities (entity_id, case_id, type, value, platform, confidence,
                   metadata_json, source_url, data_mode, sha256, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (eid, case_id, p.type, p.value, p.platform, None,
                 json.dumps(p.metadata, default=str), p.source_url, p.data_mode,
                 p.sha256, p.collected_at),
            )
        conn.commit()
    finally:
        conn.close()

    # raw scrape dump as a hashed artifact
    save_artifact(case_id, None, "json_dump",
                  json.dumps([p.to_dict() for p in profiles], indent=2, default=str),
                  suffix=".json")

    # 6: correlate -> score
    pairs = correlate(profiles)
    clusters = score(profiles, pairs, seeds=seeds)
    log_action(case_id, "scoring_complete", {"pairs": len(pairs)},
               {"clusters": len(clusters)}, "system")

    # 6b: lead reverification (live only) — for singleton LOW/REJECT entities with
    # a source_url, fetch their profile page, re-correlate against confirmed clusters
    # only, and promote those that now share a strong corroborating signal.
    # The red-herring rule (LINK_MIN_SIGNALS >= 2) is NOT weakened here.
    if config.DATA_MODE == "live":
        promoted: list[int] = []
        try:
            profiles, clusters, promoted = await reverify_leads(profiles, clusters)
            if promoted:
                for pidx in promoted:
                    log_action(
                        case_id, "lead_reverification",
                        {"entity_index": pidx, "platform": profiles[pidx].platform,
                         "value": profiles[pidx].value},
                        {"promoted": True},
                        "system",
                    )
                log_action(case_id, "reverification_summary", None,
                           {"promoted_count": len(promoted)}, "system")
        except Exception:
            pass  # reverification must never break the main pipeline

        # Flush any metadata enrichment from the reverification page-fetch back to DB
        if promoted:
            conn = get_db()
            try:
                for pidx in promoted:
                    eid = idx_to_eid.get(pidx)
                    if eid:
                        conn.execute(
                            "UPDATE entities SET metadata_json=? WHERE entity_id=?",
                            (json.dumps(profiles[pidx].metadata, default=str), eid),
                        )
                conn.commit()
            finally:
                conn.close()

    # 6c: Semantic reranking — use LLM to rerank singletons against confirmed
    # clusters' "target persona" (keywords, bios, locations, usernames). Promotes
    # high-relevance singletons into confirmed clusters and assigns relevance_rank
    # to all clusters for UI ordering. Bounded to ~6 LLM calls total.
    primary_seed = seeds[0] if seeds else {}
    rerank_promoted: list[int] = []
    try:
        clusters, rerank_promoted = await asyncio.to_thread(
            rerank_and_promote,
            primary_seed.get("type", "username"),
            primary_seed.get("value", ""),
            profiles,
            clusters,
        )
        if rerank_promoted:
            for pidx in rerank_promoted:
                log_action(
                    case_id, "rerank_promotion",
                    {"entity_index": pidx, "platform": profiles[pidx].platform,
                     "value": profiles[pidx].value},
                    {"promoted": True},
                    "system",
                )
            log_action(case_id, "rerank_summary", None,
                       {"promoted_count": len(rerank_promoted),
                        "total_clusters": len(clusters)}, "system")
        else:
            log_action(case_id, "rerank_summary", None,
                       {"promoted_count": 0, "total_clusters": len(clusters)}, "system")
    except Exception as e:
        print(f"[orchestrator] reranking failed (non-fatal): {e}")
        log_action(case_id, "rerank_error", None, {"error": str(e)}, "system")

    # LLM explanations for every multi-member cluster, fanned out concurrently. This used
    # to be a plain synchronous call inside the for-loop below — with NVIDIA unreachable
    # on some networks and each call blocking the event loop for its full timeout, a
    # ~50-cluster case could burn several minutes of dead serial wait here alone.
    explain_targets = [cl for cl in clusters if len(cl.member_indices) > 1 and cl.signals]
    explanations_by_cluster: dict[str, str] = {}
    if explain_targets:
        explain_results = await asyncio.gather(
            *[asyncio.to_thread(llm.explain_match, list(cl.signals.keys()), cl.tier)
              for cl in explain_targets],
            return_exceptions=True,
        )
        for cl, res in zip(explain_targets, explain_results):
            explanations_by_cluster[cl.cluster_id] = res if isinstance(res, str) else cl.explanation

    conn = get_db()
    try:
        for cl in clusters:
            entity_ids = [idx_to_eid[i] for i in cl.member_indices if i in idx_to_eid]
            # LLM explanation for multi-member clusters; template fallback inside the client
            explanation = explanations_by_cluster.get(cl.cluster_id, cl.explanation)
            # Include relevance metadata in signals_json for frontend consumption
            signals_data = dict(cl.signals)
            if hasattr(cl, 'relevance_score') and cl.relevance_score:
                signals_data["_relevance_score"] = cl.relevance_score
            if hasattr(cl, 'relevance_reason') and cl.relevance_reason:
                signals_data["_relevance_reason"] = cl.relevance_reason
            if hasattr(cl, 'relevance_rank') and cl.relevance_rank:
                signals_data["_relevance_rank"] = cl.relevance_rank
            if getattr(cl, 'ai_confirmed', False):
                signals_data["_ai_confirmed"] = True
                signals_data["_ai_confidence"] = cl.ai_confidence
                signals_data["_ai_reason"] = cl.ai_reason
            conn.execute(
                """INSERT INTO clusters (cluster_id, case_id, entity_ids_json, confidence_score,
                   tier, explanation, signals_json, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                (cl.cluster_id, case_id, json.dumps(entity_ids), cl.confidence_score,
                 cl.tier, explanation, json.dumps(signals_data), _now()),
            )
            # write each member's confidence onto its entity row
            for eid in entity_ids:
                conn.execute("UPDATE entities SET confidence=? WHERE entity_id=?",
                             (cl.confidence_score, eid))
        conn.commit()
    finally:
        conn.close()

    set_status(case_id, "complete")
    log_action(case_id, "investigation_complete", None,
               {"accounts": len(profiles), "clusters": len(clusters)}, "system")
    return {"status": "complete", "accounts": len(profiles), "clusters": len(clusters)}


def ingest_external_profiles(case_id: str, new_profiles: list[RawProfile]) -> dict:
    """Add externally-collected profiles (e.g. from the agentic browser) to an EXISTING
    case and RE-CORRELATE, so they are linked/scored against everything else — never
    inserted as standalone island entities that bypass the reasoning layer.

    Existing entity rows are preserved (not re-deduped/rebuilt); only clusters are
    recomputed. New profiles that duplicate an existing account (same sha256) are skipped.
    Synchronous + self-contained; safe to call from a background task via to_thread.
    Returns {added, total_entities, clusters}.
    """
    new_profiles = [p for p in (new_profiles or []) if p is not None]
    if not new_profiles:
        return {"added": 0, "total_entities": 0, "clusters": 0}

    conn = get_db()
    try:
        crow = conn.execute("SELECT seeds_json FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        if crow is None:
            return {"added": 0, "total_entities": 0, "clusters": 0, "error": "case not found"}
        seeds = json.loads((crow["seeds_json"] if crow["seeds_json"] else None) or "[]")
        seed_vals = {str(s.get("value", "")).strip().lower() for s in seeds if s.get("value")}

        # reconstruct existing entities as RawProfiles (preserves their enrichment/flags)
        rows = conn.execute(
            "SELECT * FROM entities WHERE case_id = ? ORDER BY rowid", (case_id,)).fetchall()
        profiles: list[RawProfile] = []
        eids: list[str] = []
        hashes: set[str] = set()
        for r in rows:
            md = json.loads(r["metadata_json"] or "{}")
            profiles.append(RawProfile(
                type=r["type"], value=r["value"], platform=r["platform"],
                source_url=r["source_url"] or "", metadata=md,
                data_mode=r["data_mode"] or "live", collected_at=r["created_at"] or "",
                sha256=r["sha256"] or ""))
            eids.append(r["entity_id"])
            if r["sha256"]:
                hashes.add(r["sha256"])

        # insert the new profiles (flag exact-seed match; skip exact-duplicate accounts)
        added = 0
        for p in new_profiles:
            v = str(p.value or "").strip().lower()
            u = str((p.metadata or {}).get("username") or "").strip().lower()
            if (v and v in seed_vals) or (u and u in seed_vals):
                p.metadata["exact_seed_match"] = True
            if p.sha256 and p.sha256 in hashes:
                continue
            eid = uuid.uuid4().hex
            conn.execute(
                """INSERT INTO entities (entity_id, case_id, type, value, platform, confidence,
                   metadata_json, source_url, data_mode, sha256, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (eid, case_id, p.type, p.value, p.platform, None,
                 json.dumps(p.metadata, default=str), p.source_url,
                 p.data_mode or "agentic_web", p.sha256, p.collected_at or _now()),
            )
            if p.sha256:
                hashes.add(p.sha256)
            profiles.append(p)
            eids.append(eid)
            added += 1
        conn.commit()

        # re-correlate + re-cluster over the combined set, then replace this case's clusters
        pairs = correlate(profiles)
        clusters = score(profiles, pairs, seeds=seeds)
        conn.execute("DELETE FROM clusters WHERE case_id = ?", (case_id,))
        for cl in clusters:
            entity_ids = [eids[i] for i in cl.member_indices if 0 <= i < len(eids)]
            signals_data = dict(cl.signals)
            if getattr(cl, "relevance_score", None):
                signals_data["_relevance_score"] = cl.relevance_score
            conn.execute(
                """INSERT INTO clusters (cluster_id, case_id, entity_ids_json, confidence_score,
                   tier, explanation, signals_json, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                (cl.cluster_id, case_id, json.dumps(entity_ids), cl.confidence_score,
                 cl.tier, cl.explanation, json.dumps(signals_data), _now()),
            )
            for eid in entity_ids:
                conn.execute("UPDATE entities SET confidence=? WHERE entity_id=?",
                             (cl.confidence_score, eid))
        conn.commit()
        return {"added": added, "total_entities": len(profiles), "clusters": len(clusters)}
    finally:
        conn.close()


def run_investigation_sync(case_id: str) -> dict:
    """Blocking wrapper for FastAPI BackgroundTasks.

    uvicorn sets asyncio.WindowsSelectorEventLoopPolicy() on Windows
    (venv/Lib/site-packages/uvicorn/loops/asyncio.py), and that policy is
    process-global. Since this runs as a BackgroundTask in the same process,
    a plain asyncio.run() here would inherit that policy and build a
    SelectorEventLoop, which raises NotImplementedError on any
    create_subprocess_exec call. Every CLI-based scraper (Maigret, Sherlock,
    Holehe, Blackbird, Ignorant) would then hit that inside its fail-safe
    try/except and silently return [] -- indistinguishable from "no results
    found" at every level above. Running this call on its own
    ProactorEventLoop (Windows only, scoped to this thread/instance, not the
    global policy) restores subprocess support without touching uvicorn's
    own loop.
    """
    import sys
    try:
        if sys.platform == "win32":
            loop = asyncio.ProactorEventLoop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(run_investigation(case_id))
            finally:
                asyncio.set_event_loop(None)
                loop.close()
        return asyncio.run(run_investigation(case_id))
    except Exception as e:  # noqa: BLE001
        import traceback
        tb = traceback.format_exc()
        print(f"[orchestrator] INVESTIGATION FAILED for case {case_id}:\n{tb}")
        set_status(case_id, "error")
        log_action(case_id, "investigation_error", None,
                   {"error": str(e), "traceback": tb}, "system")
        return {"status": "error", "reason": str(e)}
