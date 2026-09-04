"""
darkweb-search-hub — a small standalone search UI over three dark-web OSINT sources:

  1. Ahmia        — Darkdump's 'ahmia' engine. Clearnet-queryable, Tor Project-endorsed,
                     strictly filtered against Ahmia's own CSAM/abuse blacklist. Works with
                     no Tor running.
  2. Darkdump      — the other 5 engines the vendored darkdump_vendor.py knows about
                     (notevil, tordex, tor66, onionland, excavator). notevil/tor66/onionland/
                     excavator are Tor-only; tordex works clearnet too. Several of these are
                     UNFILTERED per upstream (tordex, tor66, onionland, excavator) — the API
                     refuses to run them unless the caller explicitly passes
                     confirm_unfiltered=true, mirroring darkdump's own CLI confirmation gate.
  3. DeepDarkCTI   — not a live query, a curated *list* (github.com/fastfire/deepdarkCTI) of
                     known dark-web forums/marketplaces/leak-sites/Telegram channels, cloned
                     locally once. "Search" here is keyword matching over that curated list.

Standalone by design (like tools/onionsearch-sandbox/) — not wired into VERTEX's main
investigation pipeline. Run separately: uvicorn main:app --port 8010
"""
from __future__ import annotations

import socket
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import darkdump_vendor as dd_mod
from deepdark_search import search_deepdarkcti, list_categories, refresh_deepdarkcti

APP_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = APP_DIR.parent / "frontend"

app = FastAPI(title="Darkweb Search Hub")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TOR_PROXY = {"http": "socks5h://localhost:9050", "https": "socks5h://localhost:9050"}

ENGINES = dd_mod.Configuration.SEARCH_ENGINES
_darkdump = dd_mod.Darkdump()

FETCHERS = {
    "ahmia": _darkdump._fetch_ahmia,
    "notevil": _darkdump._fetch_notevil,
    "tordex": _darkdump._fetch_tordex,
    "tor66": _darkdump._fetch_tor66,
    "onionland": _darkdump._fetch_onionland,
    "excavator": _darkdump._fetch_excavator,
}


def _tor_is_up(timeout=1.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 9050), timeout=timeout):
            return True
    except OSError:
        return False


def _run_engine(engine_key: str, query: str, amount: int) -> dict:
    engine = ENGINES.get(engine_key)
    if engine is None:
        return {"engine": engine_key, "ok": False, "error": "unknown engine", "results": []}

    fetcher = FETCHERS[engine_key]
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) darkweb-search-hub"}
    needs_proxy = engine["tor_required"]

    proxy_config = TOR_PROXY if needs_proxy else None
    if needs_proxy and not _tor_is_up():
        return {
            "engine": engine_key, "ok": False,
            "error": "Tor is not running on 127.0.0.1:9050 — this engine is Tor-only.",
            "results": [],
        }

    try:
        raw = fetcher(query, amount, headers, proxy_config)
        raw = raw or []
        filtered = dd_mod.Darkdump._filter_blacklisted(raw)
        return {"engine": engine_key, "ok": True, "error": None, "results": filtered,
                "filtered_count": len(raw) - len(filtered)}
    except Exception as e:  # never let one engine's failure kill the whole request
        return {"engine": engine_key, "ok": False, "error": str(e), "results": []}


@app.get("/api/health")
def health():
    tor_up = _tor_is_up()
    return {
        "status": "ok",
        "tor_running": tor_up,
        "engines": {
            key: {
                "name": e["name"],
                "tor_required": e["tor_required"],
                "filtered": e.get("filtered", True),
                "available": (not e["tor_required"]) or tor_up,
            }
            for key, e in ENGINES.items()
        },
        "deepdarkcti_categories": list_categories(),
    }


@app.get("/api/search")
def search(
    q: str = Query(..., min_length=1),
    sources: str = Query("ahmia,deepdarkcti", description="comma-separated: ahmia,darkdump,deepdarkcti"),
    darkdump_engines: str = Query("", description="comma-separated subset of notevil,tordex,tor66,onionland,excavator"),
    confirm_unfiltered: bool = Query(False),
    amount: int = Query(20, ge=1, le=100),
):
    sources_set = {s.strip().lower() for s in sources.split(",") if s.strip()}
    out = {"query": q, "started_at": time.time(), "sources": {}}

    if "ahmia" in sources_set:
        out["sources"]["ahmia"] = _run_engine("ahmia", q, amount)

    if "darkdump" in sources_set:
        requested = [e.strip().lower() for e in darkdump_engines.split(",") if e.strip()]
        requested = [e for e in requested if e in ENGINES and e != "ahmia"]
        results = {}
        for engine_key in requested:
            engine = ENGINES[engine_key]
            if not engine.get("filtered", True) and not confirm_unfiltered:
                results[engine_key] = {
                    "engine": engine_key, "ok": False,
                    "error": f"{engine['name']} is UNFILTERED (may include illegal/harmful "
                             "content). Re-run with confirm_unfiltered=true to proceed.",
                    "results": [], "requires_confirmation": True,
                }
                continue
            results[engine_key] = _run_engine(engine_key, q, amount)
        out["sources"]["darkdump"] = results

    if "deepdarkcti" in sources_set:
        out["sources"]["deepdarkcti"] = search_deepdarkcti(q)

    out["finished_at"] = time.time()
    return out


@app.post("/api/deepdarkcti/refresh")
def deepdarkcti_refresh():
    return refresh_deepdarkcti()


# Serve the single-page frontend.
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))
