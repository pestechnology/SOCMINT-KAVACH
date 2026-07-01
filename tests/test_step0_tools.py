"""
Tests for Step 0:
  1. resolve_tool() finds .bat and .cmd wrappers on Windows (extension-list fix)
  2. BlackbirdUsernameScraper parses the correct JSON fields (name / status FOUND)
  3. IgnorantScraper regex correctly identifies [+] lines and ignores [-]/[x]
"""
import asyncio
import json
import os
import re
import shutil
import sys
from datetime import datetime

import pytest

from backend.ingestion.base_module import resolve_tool, make_profile


# ---------- resolve_tool extension list ----------

def test_resolve_tool_finds_exe(tmp_path, monkeypatch):
    """resolve_tool finds a real .exe via the sys.prefix fallback (Scripts/bin subdir)."""
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    (scripts / "mytool.exe").touch()
    # sys.prefix is the venv root; resolve_tool looks at prefix/Scripts/name.exe
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    path = resolve_tool("mytool")
    assert path is not None, "resolve_tool should find mytool.exe via sys.prefix fallback"
    assert path.endswith("mytool.exe")


@pytest.mark.skipif(os.name != "nt", reason="Windows-only .bat test")
def test_resolve_tool_finds_bat(tmp_path, monkeypatch):
    """.bat wrapper in Scripts dir must be returned by resolve_tool on Windows."""
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    bat = scripts / "blackbird.bat"
    bat.write_text("@echo off\r\npython %*\r\n")
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    path = resolve_tool("blackbird")
    assert path is not None, "resolve_tool should find blackbird.bat"
    assert path.lower().endswith(".bat")


@pytest.mark.skipif(os.name != "nt", reason="Windows-only .cmd test")
def test_resolve_tool_finds_cmd(tmp_path, monkeypatch):
    """.cmd wrapper in Scripts dir must be returned by resolve_tool on Windows."""
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    (scripts / "mytool.cmd").write_text("@echo off\r\n")
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    path = resolve_tool("mytool")
    assert path is not None
    assert path.lower().endswith(".cmd")


def test_resolve_tool_returns_none_for_missing():
    """resolve_tool must return None for a tool that genuinely isn't installed."""
    assert resolve_tool("__vertex_nonexistent_tool_xyz__") is None


# ---------- Blackbird JSON parser helpers ----------

def _setup_bb_json(tmp_path, username: str, entries: list):
    """Write a Blackbird-format JSON file in the expected results subdirectory."""
    date_str = datetime.now().strftime("%m_%d_%Y")
    safe = username.replace("@", "_").replace(".", "_")
    subdir = tmp_path / "results" / f"{safe}_{date_str}_blackbird"
    subdir.mkdir(parents=True)
    jfile = subdir / f"{safe}_{date_str}_blackbird.json"
    jfile.write_text(json.dumps(entries), encoding="utf-8")
    return str(tmp_path)


def _patch_bb(monkeypatch, tmp_path):
    """Patch blackbird scraper so subprocess is a no-op and repo points to tmp_path."""
    import backend.ingestion.blackbird_scraper as bb_mod
    monkeypatch.setattr(bb_mod, "_blackbird_repo", lambda: str(tmp_path))
    monkeypatch.setattr(bb_mod, "resolve_tool", lambda _: str(tmp_path / "fake.bat"))

    async def _fake_exec(*args, **kwargs):
        class _P:
            async def communicate(self): return b"", b""
        return _P()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)


def test_blackbird_parser_reads_name_field(tmp_path, monkeypatch):
    """Parser must use 'name' key (not 'site'/'app') for platform name."""
    import backend.ingestion.blackbird_scraper as bb_mod
    repo = _setup_bb_json(tmp_path, "torvalds", [
        {"name": "GitHub", "url": "https://github.com/torvalds",
         "category": "social", "status": "FOUND", "metadata": []},
        {"name": "Twitter", "url": "https://twitter.com/torvalds",
         "category": "social", "status": "NOT-FOUND", "metadata": []},
    ])
    _patch_bb(monkeypatch, tmp_path)

    profiles = asyncio.run(bb_mod._run_blackbird("-u", "torvalds"))
    assert len(profiles) == 1, f"Expected 1 FOUND profile, got {len(profiles)}"
    assert profiles[0].platform == "github", f"Expected 'github', got {profiles[0].platform!r}"


def test_blackbird_parser_skips_non_found(tmp_path, monkeypatch):
    """Only 'FOUND' entries must be returned; ERROR/NONE/NOT-FOUND are skipped."""
    import backend.ingestion.blackbird_scraper as bb_mod
    _setup_bb_json(tmp_path, "x", [
        {"name": "A", "url": "https://a.com/x", "status": "FOUND",   "metadata": []},
        {"name": "B", "url": "https://b.com/x", "status": "ERROR",   "metadata": []},
        {"name": "C", "url": "https://c.com/x", "status": "NONE",    "metadata": []},
        {"name": "D", "url": "https://d.com/x", "status": "NOT-FOUND","metadata": []},
    ])
    _patch_bb(monkeypatch, tmp_path)

    profiles = asyncio.run(bb_mod._run_blackbird("-u", "x"))
    assert len(profiles) == 1
    assert profiles[0].platform == "a"


def test_blackbird_parser_flattens_metadata(tmp_path, monkeypatch):
    """Metadata list [{name, value}] must be flattened into the profile metadata dict."""
    import backend.ingestion.blackbird_scraper as bb_mod
    _setup_bb_json(tmp_path, "linus", [
        {"name": "LinkedIn", "url": "https://linkedin.com/in/linus",
         "status": "FOUND", "category": "professional",
         "metadata": [{"name": "fullname", "value": "Linus Torvalds"},
                       {"name": "bio",      "value": "Linux creator"}]},
    ])
    _patch_bb(monkeypatch, tmp_path)

    profiles = asyncio.run(bb_mod._run_blackbird("-u", "linus"))
    assert len(profiles) == 1
    assert profiles[0].metadata.get("fullname") == "Linus Torvalds"
    assert profiles[0].metadata.get("bio") == "Linux creator"


def test_blackbird_parser_no_exe_returns_empty(tmp_path, monkeypatch):
    """If resolve_tool returns None (blackbird not installed), _run_blackbird returns []."""
    import backend.ingestion.blackbird_scraper as bb_mod
    monkeypatch.setattr(bb_mod, "resolve_tool", lambda _: None)
    profiles = asyncio.run(bb_mod._run_blackbird("-u", "anyone"))
    assert profiles == []


def test_blackbird_parser_no_repo_returns_empty(tmp_path, monkeypatch):
    """If BLACKBIRD_PATH not set, _run_blackbird returns []."""
    import backend.ingestion.blackbird_scraper as bb_mod
    monkeypatch.setattr(bb_mod, "_blackbird_repo", lambda: None)
    monkeypatch.setattr(bb_mod, "resolve_tool", lambda _: "/fake.bat")
    profiles = asyncio.run(bb_mod._run_blackbird("-u", "anyone"))
    assert profiles == []


# ---------- IgnorantScraper regex ----------

def test_ignorant_detects_registered():
    """[+] platform.com line must result in a phone_registration profile."""
    text = (
        "Twitter : @palenath\n"
        "[+] instagram.com\n"
        "[-] amazon.com\n"
        "[x] snapchat.com\n"
        "3 websites checked in 2.0 seconds\n"
    )
    number = "+919876543210"
    profiles = []
    for plat in ("instagram", "amazon", "snapchat"):
        if re.search(rf"{plat}.*\+|\[\+\].*{plat}", text, re.I):
            profiles.append(make_profile(
                "phone_registration", number, plat, "",
                metadata={"registered": True, "source": "ignorant"},
            ))
    assert len(profiles) == 1
    assert profiles[0].platform == "instagram"


def test_ignorant_ignores_rate_limit():
    """[x] (rate-limit) must NOT be treated as registered."""
    text = "[x] snapchat.com\n[x] instagram.com\n[-] amazon.com"
    for plat in ("instagram", "amazon", "snapchat"):
        assert not re.search(rf"{plat}.*\+|\[\+\].*{plat}", text, re.I), \
            f"{plat} should not match on [x] line"


def test_ignorant_detects_all_three():
    """When all three platforms show [+], all three must be returned."""
    text = "[+] instagram.com\n[+] amazon.com\n[+] snapchat.com"
    count = 0
    for plat in ("instagram", "amazon", "snapchat"):
        if re.search(rf"{plat}.*\+|\[\+\].*{plat}", text, re.I):
            count += 1
    assert count == 3
