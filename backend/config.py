"""
backend/config.py — central configuration for VERTEX.

Loads from a .env file (see .env.example). NEVER hardcode secrets here.
validate_keys() WARNS about missing keys but never crashes — the fail-safe
principle applies to config too: a missing key just disables the tools that
need it, it never stops the app from booting.
"""
from __future__ import annotations

import os
from pathlib import Path

# Trust the OS certificate store for all outbound TLS. On managed/corporate
# networks (e.g. a TLS-inspection proxy) or for hosts that serve an incomplete
# chain, Python's bundled certifi store rejects certs that the OS store accepts,
# so httpx scrapers fail with CERTIFICATE_VERIFY_FAILED and (being fail-safe)
# silently return []. truststore makes Python use the OS store instead. This
# STILL verifies certificates — it is not the same as disabling verification.
# No-op if truststore is unavailable or injection fails.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

# Load .env if python-dotenv is available (optional dependency).
try:
    from dotenv import load_dotenv

    _ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(_ENV_PATH)
except Exception:  # pragma: no cover - dotenv is optional
    pass


def _get(key: str, default: str = "") -> str:
    val = os.getenv(key, default)
    return val.strip() if isinstance(val, str) else val


def _get_bool(key: str, default: bool = False) -> bool:
    return _get(key, str(default)).lower() in {"1", "true", "yes", "on"}


# ---- Data mode ----
DATA_MODE: str = _get("DATA_MODE", "live").lower()          # "live" | "mock"
DEMO_FALLBACK_ENABLED: bool = _get_bool("DEMO_FALLBACK_ENABLED", True)

# ---- API keys ----
SERPER_API_KEY: str = _get("SERPER_API_KEY")
# Brave Search API — a second, independent search index run in parallel with Serper
# (see brave_scraper.py). Optional: the scraper returns [] with no key, same fail-safe
# contract as every other optional-key source.
BRAVE_API_KEY: str = _get("BRAVE_API_KEY")
SUPADATA_API_KEY: str = _get("SUPADATA_API_KEY")  # web scrape API (anti-bot bypass)
INTELBASE_API_KEY: str = _get("INTELBASE_API_KEY")  # breach/OSINT lookup API (email/username/phone)
# Route entity/fact extraction for Indic-script text to Gemini/IndicNER instead of Llama.
# OFF by default; the deterministic normalization layer does not depend on this.
INDIC_EXTRACTION_ENABLED: bool = _get("INDIC_EXTRACTION_ENABLED", "false").lower() == "true"
GITHUB_TOKEN: str = _get("GITHUB_TOKEN")
NVIDIA_API_KEY: str = _get("NVIDIA_API_KEY")
NVIDIA_BASE_URL: str = _get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
HIBP_API_KEY: str = _get("HIBP_API_KEY")
NUMVERIFY_KEY: str = _get("NUMVERIFY_KEY")
# Both free-tier keys (sign up at gravatar.com/developers and emailrep.io) — as of
# 2025 both services require a key even for basic/public lookups, so these are NOT
# truly "no key" despite older docs; the scrapers below degrade gracefully without one
# (Gravatar still does a free no-key avatar-existence check; EmailRep returns []).
GRAVATAR_API_KEY: str = _get("GRAVATAR_API_KEY")
EMAILREP_API_KEY: str = _get("EMAILREP_API_KEY")
TELEGRAM_API_ID: str = _get("TELEGRAM_API_ID")
TELEGRAM_API_HASH: str = _get("TELEGRAM_API_HASH")
# NewLeaks OSINT Telegram bot (@NewleaksOsintBot) — an OPTIONAL add-on breach/PII source
# queried by messaging the bot over a Telethon USER session (bots can't message bots).
# Fully inert unless NEWLEAKS_ENABLED=true AND a user .session file exists — see
# newleaks_scraper.py. NEWLEAKS_API_KEY is stored for a possible in-chat auth step; the
# actual lookup goes through the user session, not this key.
NEWLEAKS_ENABLED: bool = _get_bool("NEWLEAKS_ENABLED", False)
NEWLEAKS_BOT_USERNAME: str = _get("NEWLEAKS_BOT_USERNAME", "NewleaksOsintBot")
NEWLEAKS_API_KEY: str = _get("NEWLEAKS_API_KEY")
NEWLEAKS_TIMEOUT_SECONDS: int = int(_get("NEWLEAKS_TIMEOUT_SECONDS", "25"))
# Path (no extension) for the Telethon USER session created by scripts/telegram_login.py.
# _ROOT is defined further down, so compute the project root inline here.
TELEGRAM_USER_SESSION: str = _get(
    "TELEGRAM_USER_SESSION", str(Path(__file__).resolve().parent.parent / "user_session"))
# Reddit app-only OAuth (free "script"/"web" app). When set, the Reddit scraper uses
# oauth.reddit.com instead of the public endpoint, which avoids the anti-bot 403s that
# block datacenter IPs and makes activity analysis reliable on any network.
REDDIT_CLIENT_ID: str = _get("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET: str = _get("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT: str = _get("REDDIT_USER_AGENT", "VERTEX-OSINT/1.0 (CIDECODE)")

# Deeper breach coverage (paid APIs; both scrapers return [] with no key configured —
# see dehashed_scraper.py / leakcheck_scraper.py for the fail-safe stub behaviour).
DEHASHED_EMAIL: str = _get("DEHASHED_EMAIL")
DEHASHED_API_KEY: str = _get("DEHASHED_API_KEY")
LEAKCHECK_API_KEY: str = _get("LEAKCHECK_API_KEY")

# ---- LLM model names (NVIDIA Cloud, OpenAI-compatible) ----
# NOTE (2026-09-01): NVIDIA retired meta/llama-3.3-70b-instruct and
# deepseek-ai/deepseek-v4-pro from the integrate.api.nvidia.com catalog (both now
# 410 Gone) — a valid NVIDIA_API_KEY alone is NOT enough, the model id itself has to
# still exist. The two defaults below were verified live against /v1/chat/completions
# (HTTP 200) on that date; re-check https://integrate.api.nvidia.com/v1/models if
# either goes 410 again, and override via .env rather than editing here.
LLM_EXTRACT_MODEL: str = _get("LLM_EXTRACT_MODEL", "openai/gpt-oss-120b")
LLM_EXPLAIN_MODEL: str = _get("LLM_EXPLAIN_MODEL", "nvidia/nemotron-3-super-120b-a12b")
LLM_TIMEOUT_SECONDS: int = int(_get("LLM_TIMEOUT_SECONDS", "45"))

# ---- Groq Cloud (reranking + failover) ----
GROQ_API_KEY: str = _get("GROQ_API_KEY")
GROQ_BASE_URL: str = _get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL: str = _get("GROQ_MODEL", "llama-3.3-70b-versatile")

# ---- Case chat assistant (grounded Q&A over a single case's data) ----
# A DEDICATED NVIDIA key can be set here so the interactive chat doesn't compete with the
# investigation pipeline's quota (the pipeline is Groq-first / NVIDIA-fallback; the chat is
# NVIDIA-first by request). Falls back to the main NVIDIA key when unset, and the answerer
# further falls back to the Groq path — so it works with zero extra config.
CHAT_NVIDIA_API_KEY: str = _get("CHAT_NVIDIA_API_KEY") or NVIDIA_API_KEY
CHAT_NVIDIA_BASE_URL: str = _get("CHAT_NVIDIA_BASE_URL", NVIDIA_BASE_URL)
# meta/llama-3.1-70b-instruct (the prior default) and meta/llama-3.1-8b-instruct (the
# prior low-latency fallback) were both retired from NVIDIA's catalog as of 2026-09-01
# (410 Gone) alongside the two models above. Reusing the same verified-working
# openai/gpt-oss-120b here until a dedicated low-latency replacement is verified —
# see the LLM_EXTRACT_MODEL note above for how to re-check the catalog.
CHAT_LLM_MODEL: str = _get("CHAT_LLM_MODEL", "openai/gpt-oss-120b")

# ---- Paths ----
_ROOT = Path(__file__).resolve().parent.parent
DB_PATH: str = _get("DB_PATH", str(_ROOT / "cidecode.db"))
REPORT_OUTPUT_DIR: str = _get("REPORT_OUTPUT_DIR", str(_ROOT / "reports"))
SYNTHETIC_DATA_PATH: str = _get("SYNTHETIC_DATA_PATH", str(_ROOT / "data" / "synthetic_dataset.json"))

# ---- Auth ----
JWT_SECRET: str = _get("JWT_SECRET", "dev-only-insecure-secret-change-me")
TOKEN_EXPIRY_HOURS: int = int(_get("TOKEN_EXPIRY_HOURS", "8"))

# Keys that are genuinely required for the core demo to be impressive.
_REQUIRED = {
    "SERPER_API_KEY": SERPER_API_KEY,
    "GITHUB_TOKEN": GITHUB_TOKEN,
    "NVIDIA_API_KEY": NVIDIA_API_KEY,
}
# Keys that improve coverage but are not required.
_OPTIONAL = {
    "BRAVE_API_KEY": BRAVE_API_KEY,
    "HIBP_API_KEY": HIBP_API_KEY,
    "NUMVERIFY_KEY": NUMVERIFY_KEY,
    "TELEGRAM_API_ID": TELEGRAM_API_ID,
    "TELEGRAM_API_HASH": TELEGRAM_API_HASH,
    "DEHASHED_API_KEY": DEHASHED_API_KEY,
    "LEAKCHECK_API_KEY": LEAKCHECK_API_KEY,
    "GRAVATAR_API_KEY": GRAVATAR_API_KEY,
    "EMAILREP_API_KEY": EMAILREP_API_KEY,
}


def validate_keys() -> dict[str, list[str]]:
    """Warn (never crash) about missing keys. Returns {"missing_required": [...],
    "missing_optional": [...]} so callers/tests can inspect the result."""
    missing_required = [k for k, v in _REQUIRED.items() if not v]
    missing_optional = [k for k, v in _OPTIONAL.items() if not v]

    if missing_required:
        print(f"[config] WARNING: missing REQUIRED keys: {', '.join(missing_required)} "
              f"- the tools that use them will return empty results.")
    if missing_optional:
        print(f"[config] note: missing optional keys: {', '.join(missing_optional)} "
              f"- related tools are disabled but the pipeline still runs.")
    if JWT_SECRET == "dev-only-insecure-secret-change-me":
        print("[config] WARNING: JWT_SECRET is the insecure default - set a real one in .env.")
    if DATA_MODE not in ("live", "mock"):
        print(f"[config] WARNING: DATA_MODE='{DATA_MODE}' is invalid; expected 'live' or 'mock'.")

    return {"missing_required": missing_required, "missing_optional": missing_optional}
