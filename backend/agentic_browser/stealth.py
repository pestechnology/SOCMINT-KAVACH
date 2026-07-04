"""Stealth configuration for Playwright / browser automation context."""
from typing import Any, Dict
from .config import DEFAULT_USER_AGENT, STEALTH_CHROMIUM_ARGS, HEADLESS_BROWSER


def get_playwright_launch_options() -> Dict[str, Any]:
    """Returns chromium launch arguments configured for stealth navigation."""
    return {
        "headless": HEADLESS_BROWSER,
        "args": STEALTH_CHROMIUM_ARGS,
        "ignore_default_args": ["--enable-automation"],
    }


def get_stealth_context_options() -> Dict[str, Any]:
    """Returns browser context options to mask automation fingerprints."""
    return {
        "user_agent": DEFAULT_USER_AGENT,
        "viewport": {"width": 1280, "height": 800},
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "permissions": [],
        "java_script_enabled": True,
        "bypass_csp": True,
        "extra_http_headers": {
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="124", "Chromium";v="124"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
        },
    }
