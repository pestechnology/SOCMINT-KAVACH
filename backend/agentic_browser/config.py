"""Configuration settings for the VERTEX Agentic Web Browser module."""
import os

# Mode: "auto" (use live browser-use if installed + a Gemini key is set, else unavailable),
# "live" (force live), or "off" (disabled). There is deliberately NO "simulated" mode that
# fabricates data — an OSINT tool must never invent profiles.
AGENTIC_BROWSER_MODE = os.getenv("AGENTIC_BROWSER_MODE", "auto").lower()

# ---- LLM that drives the browser: Gemini (free tier, fast, vision-capable) ----
# Navigation/vision runs on Gemini; NVIDIA is far too slow for a multi-step agent loop.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Browser launch settings
HEADLESS_BROWSER = os.getenv("HEADLESS_BROWSER", "true").lower() == "true"
BROWSER_TIMEOUT_MS = int(os.getenv("BROWSER_TIMEOUT_MS", "30000"))
MAX_STEPS_PER_TASK = int(os.getenv("MAX_STEPS_PER_TASK", "12"))
# Hard wall-clock ceiling for one agent task, and per-step ceiling (fail-safe: never hang).
TASK_TIMEOUT_S = int(os.getenv("AGENTIC_TASK_TIMEOUT_S", "120"))
STEP_TIMEOUT_S = int(os.getenv("AGENTIC_STEP_TIMEOUT_S", "45"))
# Browsers are heavy (100s of MB each) — cap concurrent live agents so a burst can't OOM.
MAX_CONCURRENT_TASKS = int(os.getenv("AGENTIC_MAX_CONCURRENT", "2"))

# Default User-Agent for stealth navigation
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Chromium automation arguments to bypass Cloudflare Turnstile and basic bot detection
STEALTH_CHROMIUM_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-accelerated-2d-canvas",
    "--no-first-run",
    "--no-service-autorun",
    "--password-store=basic",
]
