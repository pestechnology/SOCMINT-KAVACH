"""
backend/ingestion/base_module.py — the core data-source abstraction.

EVERYTHING downstream depends on this. Two pieces:

    RawProfile      — the one object every scraper emits (Section 5A.5 / 6.1)
    BaseDataSource  — abstract base; resolve() is fail-safe (returns [], never raises)

The fail-safe contract is the reason one broken scraper never stops the run.
"""
from __future__ import annotations

import datetime
import hashlib
import os
import shutil
import sys
from dataclasses import dataclass, field


def resolve_tool(name: str) -> str | None:
    """Find a CLI tool's executable path.

    `asyncio.create_subprocess_exec("maigret", ...)` fails on Windows when the venv's
    Scripts dir isn't on PATH (e.g. the backend is launched via venv\\Scripts\\python.exe
    without activation) — so maigret/holehe/sherlock/blackbird/ignorant silently return
    []. This resolves the tool against PATH first, then the running interpreter's
    Scripts/bin dir, so CLI scrapers work regardless of how the server was started.
    Returns None if the tool genuinely isn't installed.
    """
    found = shutil.which(name)
    if found:
        return found
    # shutil.which() only searches PATH; when the venv's Scripts dir isn't on PATH
    # (e.g. server launched via venv\Scripts\python.exe without activation), it misses
    # even properly-installed tools.  Fall back to the interpreter's Scripts/bin dir.
    # On Windows try .exe first, then .bat/.cmd for wrapper scripts (e.g. blackbird.bat).
    exts = [".exe", ".bat", ".cmd"] if os.name == "nt" else [""]
    sub = "Scripts" if os.name == "nt" else "bin"
    for base in (os.path.dirname(sys.executable), sys.prefix):
        for ext in exts:
            cand = os.path.join(base, sub, name + ext)
            if os.path.exists(cand):
                return cand
    return None


@dataclass
class RawProfile:
    type: str                       # social_account | email | phone | username | upi | breach | post | name | archive | ...
    value: str                      # the actual identifier or content
    platform: str                   # instagram | github | telegram | hibp | ...
    source_url: str                 # where it was found
    metadata: dict = field(default_factory=dict)   # bio, photo_url, photo_phash, followers, posting_history, ...
    data_mode: str = "live"         # live | mock
    collected_at: str = ""          # ISO timestamp
    sha256: str = ""                # hash of value+platform+source_url (evidence integrity)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "value": self.value,
            "platform": self.platform,
            "source_url": self.source_url,
            "metadata": self.metadata,
            "data_mode": self.data_mode,
            "collected_at": self.collected_at,
            "sha256": self.sha256,
        }


def _hash(*parts) -> str:
    """SHA-256 of the joined parts. Used for evidence-integrity hashes."""
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def make_profile(type: str, value: str, platform: str, source_url: str,
                 metadata: dict | None = None, data_mode: str = "live") -> RawProfile:
    """Helper that stamps collected_at and sha256 consistently for every scraper."""
    return RawProfile(
        type=type,
        value=value,
        platform=platform,
        source_url=source_url,
        metadata=metadata or {},
        data_mode=data_mode,
        collected_at=_now(),
        sha256=_hash(value, platform, source_url),
    )


class BaseDataSource:
    """Abstract scraper. Subclasses implement _run_live(); resolve() is fail-safe."""

    name: str = "base"

    async def resolve(self, identifier: str, data_mode: str = "live") -> list[RawProfile]:
        """Public entrypoint. NEVER raises — returns [] on any failure."""
        try:
            if data_mode == "mock":
                return self._run_mock(identifier)
            return await self._run_live(identifier)
        except Exception as e:  # noqa: BLE001 - fail-safe by design
            print(f"[{self.name}] failed: {e}")
            return []

    async def _run_live(self, identifier: str) -> list[RawProfile]:
        raise NotImplementedError

    def _run_mock(self, identifier: str) -> list[RawProfile]:
        """Override in dev scrapers; default to empty."""
        return []
