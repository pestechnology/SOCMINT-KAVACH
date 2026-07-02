"""
backend/pipeline/orchestrator.py — runs one investigation end to end.

run_investigation(case_id) (async) and run_investigation_sync(case_id) (for
FastAPI BackgroundTasks). Flow:

  1. read case seeds
  2. for each seed, fan out the applicable scrapers in parallel (asyncio.gather,
     return_exceptions=True so one failure never kills the batch)
  3. one-level cascade: any derived username/phone seed (e.g. from a UPI) is run
     through its own tools
  4. LLM entity-extraction on free-text blobs (bios/snippets) -> extra seeds folded in
  5. dedup -> persist entities (streaming: written as soon as scraping is done)
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
from backend.ingestion.base_module import RawProfile
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
from backend.ingestion.photo_enrich import enrich_photos
from backend.ingestion.profile_page_fetcher import enrich_profiles_from_page
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
        "email":    [HIBPScraper(), XposedOrNotScraper(), HoleheScraper(), BlackbirdEmailScraper(), GitHubScraper(), SerperScraper('"{q}"')],
        # NumVerify (carrier/line-type/country) works with the configured key; a PLAIN
        # Serper search returns real web mentions, whereas the old site:truecaller.com
        # dork returned nothing (Truecaller blocks indexing). PhoneInfoga/ignorant stay
        # (fail-safe if their server/CLI is absent); HIBP is email-only and the Facebook
        # checker is a stub, so both are dropped from the phone path.
        "phone":    [NumVerifyScraper(), PhoneInfogaScraper(), IgnorantScraper(), SerperScraper('"{q}"')],
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
                     SerperScraper('"{q}"')],
        "face":     [],   # handled separately (pHash against collected photos)
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

FOREIGN_LOCATIONS = {
    "usa", "united states", "canada", "uk", "united kingdom", "london", "england",
    "germany", "berlin", "france", "paris", "china", "beijing", "tokyo", "japan",
    "brazil", "australia", "sydney", "toronto", "new york", "california", "ca, us",
    "ny, us", "texas", "tx, us", "chicago", "florida", "russia", "moscow", "spain",
    "madrid", "italy", "rome", "netherlands", "amsterdam", "singapore", "malaysia",
    "indonesia", "vietnam", "thailand", "philippines", "egypt", "south africa",
    "nigeria", "kenya", "mexico", "argentina", "colombia", "chile", "peru",
    "poland", "ukraine", "sweden", "norway", "denmark", "finland", "ireland",
    "scotland", "wales", "new zealand", "switzerland", "austria", "belgium",
    "greece", "turkey", "israel", "uae", "dubai", "saudi arabia", "qatar",
    "kuwait", "seoul", "korea", "hong kong", "taiwan", "vancouver", "montreal",
    "melbourne", "brisbane", "auckland", "dublin", "munich", "hamburg", "frankfurt",
    "barcelona", "milan", "lisbon", "prague", "warsaw", "budapest", "vienna",
    "zurich", "geneva", "brussels", "copenhagen", "stockholm", "oslo", "helsinki",
    "edinburgh", "manchester", "birmingham", "seattle", "boston", "san francisco",
    "los angeles", "austin", "houston", "atlanta", "miami", "denver", "phoenix",
    "philadelphia", "portland", "sandiego", "dallas", "washington", "detroit",
}

INDIAN_LOCATIONS = {
    "india", "in", "ind", "bharat", "delhi", "new delhi", "mumbai", "bangalore",
    "bengaluru", "hyderabad", "chennai", "kolkata", "pune", "ahmedabad", "jaipur",
    "surat", "lucknow", "kanpur", "nagpur", "indore", "thane", "bhopal",
    "visakhapatnam", "patna", "vadodara", "ghaziabad", "ludhiana", "agra",
    "nashik", "faridabad", "meerut", "rajkot", "kalyan", "vasai", "varanasi",
    "srinagar", "aurangabad", "dhanbad", "amritsar", "navi mumbai", "allahabad",
    "howrah", "ranchi", "gwalior", "jabalpur", "coimbatore", "vijayawada",
    "jodhpur", "madurai", "raipur", "kota", "chandigarh", "guwahati", "solapur",
    "hubli", "mysore", "mysuru", "tiruchirappalli", "bareilly", "aligarh",
    "tiruppur", "gurgaon", "gurugram", "noida", "kochi", "cochin", "trivandrum",
    "thiruvananthapuram", "bhubaneswar", "salem", "warangal", "jalgaon",
    "guntur", "bikaner", "amravati", "goa", "kerala", "tamil nadu", "karnataka",
    "maharashtra", "gujarat", "rajasthan", "uttar pradesh", "west bengal",
    "telangana", "andhra pradesh", "bihar", "punjab", "haryana", "odisha",
    "assam", "uttarakhand", "jharkhand", "chhattisgarh", "himachal pradesh",
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
    # 0. Non-social / hard seed records (upi, email, phone, breach, name, archive, etc.) are always kept
    if p.type not in ("social_account", "web_page"):
        return True

    plat = (p.platform or "").lower().strip()
    m = p.metadata or {}

    # 1. Country check (India focus):
    # If explicit location exists and points to a foreign country outside India, drop it.
    loc = str(m.get("location") or "").lower()
    if loc:
        has_foreign = any(fl in loc for fl in FOREIGN_LOCATIONS)
        has_indian = any(il in loc for il in INDIAN_LOCATIONS)
        if has_foreign and not has_indian:
            return False

    # 2. Legitimate website / rich data check for social/web accounts:
    # Keep if it is a major known legitimate platform
    is_legit_plat = any(legit in plat for legit in LEGITIMATE_PLATFORMS)
    if is_legit_plat:
        return True

    # If not a known major platform, ONLY keep it if it has rich verifiable data
    # (name, email, phone, or bio > 15 chars). Ignore fake/useless websites with no data!
    has_rich_data = bool(
        m.get("name") or m.get("fullname") or m.get("email") or m.get("phone")
        or (m.get("bio") and len(str(m.get("bio"))) > 15)
    )
    return has_rich_data


def _dedup(profiles: list[RawProfile]) -> list[RawProfile]:
    out: list[RawProfile] = []
    seen_social: dict[tuple[str, str], RawProfile] = {}
    seen_other: dict[tuple[str, str, str], RawProfile] = {}

    for p in profiles:
        if not _is_legitimate_and_target_country(p):
            continue
        plat = p.platform.lower()
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

    # 1. Username Permutation Engine & Auto-Correction
    expanded_seeds = []
    for s in seeds:
        # If user typed a full name (with spaces) into a username seed, auto-correct to name!
        if s.get("type") == "username" and isinstance(s.get("value"), str) and " " in s["value"].strip():
            s["type"] = "name"
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

    # 3: one-level cascade for derived seeds (e.g. UPI -> username/phone)
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
        extract_tasks = [_extract(b) for b in blobs[:10]]
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
    if config.DATA_MODE == "live":
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

        def _has_content_metadata(p: RawProfile) -> bool:
            if p.type not in ("social_account", "username"):
                return True
            meta = getattr(p, "metadata", {}) or {}
            boilerplate = {"tags", "all_ids", "source", "site_name", "registered", "service", "derived_from", "cascade", "username", "id", "url", "note", "raw_line", "error"}
            for k, v in meta.items():
                if k not in boilerplate and v not in (None, "", [], {}, "null", "None", 0):
                    return True
            return False

        before_meta = len(profiles)
        profiles = [p for p in profiles if _has_content_metadata(p)]
        if len(profiles) != before_meta:
            log_action(case_id, "empty_metadata_filter", {"before": before_meta}, {"after": len(profiles)}, "system")
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

    conn = get_db()
    try:
        for cl in clusters:
            entity_ids = [idx_to_eid[i] for i in cl.member_indices if i in idx_to_eid]
            # LLM explanation for multi-member clusters; template fallback inside the client
            explanation = cl.explanation
            if len(cl.member_indices) > 1 and cl.signals:
                explanation = llm.explain_match(list(cl.signals.keys()), cl.tier)
            # Include relevance metadata in signals_json for frontend consumption
            signals_data = dict(cl.signals)
            if hasattr(cl, 'relevance_score') and cl.relevance_score:
                signals_data["_relevance_score"] = cl.relevance_score
            if hasattr(cl, 'relevance_reason') and cl.relevance_reason:
                signals_data["_relevance_reason"] = cl.relevance_reason
            if hasattr(cl, 'relevance_rank') and cl.relevance_rank:
                signals_data["_relevance_rank"] = cl.relevance_rank
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
