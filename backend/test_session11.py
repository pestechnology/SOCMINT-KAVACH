"""Gate tests for Session 11: Phone & UPI handling."""

import asyncio
import re
import shutil
from unittest.mock import patch

from backend.datasources._helpers import normalize_phone
from backend.datasources.ignorant_scraper import IgnorantScraper
from backend.datasources.maigret import MaigretScraper
from backend.datasources.phoneinfoga import PhoneInfogaScraper
from backend.datasources.upi import UPIParser
from backend.orchestrator import run_investigation
from backend.schemas import Identifier, IdentifierType, RawProfile


def test_normalize_phone_cases():
    print("Running test_normalize_phone_cases...")
    assert normalize_phone("9876543210") == "+919876543210"
    assert normalize_phone("+91 98765-43210") == "+919876543210"
    assert normalize_phone("09876543210") == "+919876543210"
    assert normalize_phone("+1 (555) 0199") == "+15550199"
    print("  PASSED")


async def test_phoneinfoga_parse_output():
    print("Running test_phoneinfoga_parse_output...")

    async def fake_exec(*args, **kwargs):
        class FakeProc:
            returncode = 0

            async def communicate(self):
                return b"Found: https://numverify.com\nAlso https://truecaller.com", b""

        return FakeProc()

    with patch("asyncio.create_subprocess_exec", fake_exec), patch("shutil.which", lambda x: "/usr/bin/phoneinfoga"):
        s = PhoneInfogaScraper()
        res = await s.resolve(Identifier(type=IdentifierType.PHONE, value="9876543210"))
        assert len(res) == 2
        assert res[0].value == "+919876543210"
        assert res[0].type == "phone_lookup"
    print("  PASSED")


async def test_ignorant_handle_sync():
    print("Running test_ignorant_handle_sync...")

    async def fake_to_thread(func, *args, **kwargs):
        return [
            {"name": "amazon", "exists": True},
            {"name": "instagram", "exists": False},
            {"name": "snapchat", "exists": True},
        ]

    with patch("asyncio.to_thread", fake_to_thread):
        s = IgnorantScraper()
        res = await s.resolve(Identifier(type=IdentifierType.PHONE, value="9876543210"))
        assert len(res) == 2
        assert {r.platform for r in res} == {"amazon", "snapchat"}
        assert all(r.type == "phone_registration" for r in res)
    print("  PASSED")


async def test_upi_parser():
    print("Running test_upi_parser...")
    s = UPIParser()
    res = await s.resolve(Identifier(type=IdentifierType.UPI, value="ramesh.k@okaxis"))
    assert len(res) == 1
    assert res[0].type == "upi_id"
    assert res[0].value == "ramesh.k@okaxis"
    assert res[0].metadata["username_prefix"] == "ramesh.k"
    assert res[0].metadata["bank_handle"] == "okaxis"
    print("  PASSED")


async def test_upi_cascade():
    print("Running test_upi_cascade...")

    async def fake_maigret_resolve(self, identifier):
        if identifier.value == "ramesh.k":
            return [
                RawProfile(
                    type="social_account",
                    value="ramesh.k",
                    platform="github",
                    source_url="https://github.com/ramesh.k",
                    data_mode="live",
                    metadata={"fullname": "Ramesh K", "bio": "", "photo_url": "", "source_tool": "maigret", "source_query": "ramesh.k"},
                    collected_at="2026-01-01T00:00:00",
                    sha256="abc",
                )
            ]
        return []

    with patch.object(MaigretScraper, "resolve", fake_maigret_resolve):
        profiles, clusters = await run_investigation("ramesh.k@okaxis", IdentifierType.UPI)
        types = {p.type for p in profiles}
        assert "upi_id" in types, f"Expected upi_id in {types}"
        assert "social_account" in types, f"Expected social_account in {types}"
    print("  PASSED")


async def main():
    test_normalize_phone_cases()
    await test_phoneinfoga_parse_output()
    await test_ignorant_handle_sync()
    await test_upi_parser()
    await test_upi_cascade()
    print("\n=== ALL SESSION 11 GATE TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
