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
GITHUB_TOKEN: str = _get("GITHUB_TOKEN")
NVIDIA_API_KEY: str = _get("NVIDIA_API_KEY")
NVIDIA_BASE_URL: str = _get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
HIBP_API_KEY: str = _get("HIBP_API_KEY")
NUMVERIFY_KEY: str = _get("NUMVERIFY_KEY")
TELEGRAM_API_ID: str = _get("TELEGRAM_API_ID")
TELEGRAM_API_HASH: str = _get("TELEGRAM_API_HASH")

# ---- LLM model names (NVIDIA Cloud, OpenAI-compatible) ----
LLM_EXTRACT_MODEL: str = _get("LLM_EXTRACT_MODEL", "meta/llama-3.3-70b-instruct")
LLM_EXPLAIN_MODEL: str = _get("LLM_EXPLAIN_MODEL", "deepseek-ai/deepseek-v4-pro")
LLM_TIMEOUT_SECONDS: int = int(_get("LLM_TIMEOUT_SECONDS", "15"))

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
    "HIBP_API_KEY": HIBP_API_KEY,
    "NUMVERIFY_KEY": NUMVERIFY_KEY,
    "TELEGRAM_API_ID": TELEGRAM_API_ID,
    "TELEGRAM_API_HASH": TELEGRAM_API_HASH,
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
