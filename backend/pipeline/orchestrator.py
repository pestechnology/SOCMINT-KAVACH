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
                     SerperScraper('site:twitter.com "{q}"')],
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
    # "name" is included so that web_mention results from a name search all carry
    # metadata["name"] = seed_value, causing exact_name_match (35 pts) to fire between
    # them and promote them from REJECT (invisible) to LOW (visible, orange) in the UI.
    if seed_type in {"email", "phone", "username", "name"}:
        for p in profiles:
            if seed_type not in p.metadata:
                p.metadata[seed_type] = value
    return profiles


def _dedup(profiles: list[RawProfile]) -> list[RawProfile]:
    out: list[RawProfile] = []
    seen_social: dict[tuple[str, str], RawProfile] = {}
    seen_other: dict[tuple[str, str, str], RawProfile] = {}

    for p in profiles:
        plat = p.platform.lower()
        val = (p.value or "").lower()

        if p.type == "social_account":
            key = (plat, val)
            if key in seen_social:
                existing = seen_social[key]
                # Merge metadata
                existing.metadata = {**p.metadata, **existing.metadata}
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
                existing.metadata = {**p.metadata, **existing.metadata}
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

    # 1. Username Permutation Engine
    expanded_seeds = []
    for s in seeds:
        expanded_seeds.append(s)
        if s.get("type") in ("name", "username") and isinstance(s.get("value"), str):
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
                if ("username", v.lower()) not in searched and v not in variant_set:
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
                    if ent.get("type") in ("username", "email") and ent.get("value"):
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
    clusters = score(profiles, pairs)
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

    conn = get_db()
    try:
        for cl in clusters:
            entity_ids = [idx_to_eid[i] for i in cl.member_indices]
            # LLM explanation for multi-member clusters; template fallback inside the client
            explanation = cl.explanation
            if len(cl.member_indices) > 1 and cl.signals:
                explanation = llm.explain_match(list(cl.signals.keys()), cl.tier)
            conn.execute(
                """INSERT INTO clusters (cluster_id, case_id, entity_ids_json, confidence_score,
                   tier, explanation, signals_json, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                (cl.cluster_id, case_id, json.dumps(entity_ids), cl.confidence_score,
                 cl.tier, explanation, json.dumps(cl.signals), _now()),
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
