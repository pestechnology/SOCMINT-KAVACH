"""
backend/ingestion/phone_scrapers.py — phone-seed scrapers.

  IgnorantScraper    — `ignorant` CLI: is the number registered on IG/Amazon/Snapchat?
  PhoneInfogaScraper — PhoneInfoga REST API (or binary) for carrier/country/line type.

Both are fail-safe: if the tool/binary/server isn't present, they return []. The
Playwright-based checks (FacebookPhoneChecker, UPINameLookup) are intentionally NOT
auto-run — they are the most fragile/legally-sensitive and are left as opt-in.
"""
from __future__ import annotations

import asyncio
import json
import re

import httpx

from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile


def _split_phone(number: str) -> tuple[str, str]:
    digits = re.sub(r"\D", "", number)
    if number.strip().startswith("+"):
        # naive split: assume last 10 are national number, rest is country code
        cc, nat = digits[:-10] or "91", digits[-10:]
    else:
        cc, nat = "91", digits[-10:]
    return cc, nat


class IgnorantScraper(BaseDataSource):
    name = "ignorant"

    async def _run_live(self, number: str) -> list[RawProfile]:
        cc, nat = _split_phone(number)
        proc = await asyncio.create_subprocess_exec(
            "ignorant", cc, nat,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        text = out.decode(errors="ignore")
        profiles = []
        for plat in ("instagram", "amazon", "snapchat"):
            if re.search(rf"{plat}.*\+|\[\+\].*{plat}", text, re.I):
                profiles.append(make_profile(
                    "phone_registration", number, plat, "",
                    metadata={"registered": True, "source": "ignorant"},
                ))
        return profiles


class PhoneInfogaScraper(BaseDataSource):
    name = "phoneinfoga"

    def __init__(self, base_url: str = "http://localhost:5000"):
        self.base_url = base_url.rstrip("/")

    async def _run_live(self, number: str) -> list[RawProfile]:
        digits = re.sub(r"\D", "", number)
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{self.base_url}/api/numbers/{digits}/scan/local")
            if r.status_code != 200:
                return []
            data = r.json()
        try:
            d = data if isinstance(data, dict) else json.loads(data)
        except Exception:
            return []
        return [make_profile(
            "phone_intel", number, "phoneinfoga", "",
            metadata={
                "country": d.get("country") or d.get("Country"),
                "carrier": d.get("carrier") or d.get("Carrier"),
                "line_type": d.get("lineType") or d.get("Type"),
                "valid": d.get("valid", d.get("Valid")),
            },
        )]


class NumVerifyScraper(BaseDataSource):
    name = "numverify"

    async def _run_live(self, number: str) -> list[RawProfile]:
        from backend import config
        import os
        api_key = os.environ.get("NUMVERIFY_KEY") or getattr(config, "NUMVERIFY_KEY", None)
        if not api_key:
            return []
            
        digits = re.sub(r"\D", "", number)
        url = f"http://apilayer.net/api/validate?access_key={api_key}&number={digits}"
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(url)
                if r.status_code != 200:
                    return []
                data = r.json()
                
                if data.get("valid") is False and not data.get("country_code"):
                    # API error or invalid number format
                    return []
                    
                return [make_profile(
                    "phone_intel", number, "numverify", "",
                    metadata={
                        "country": data.get("country_name"),
                        "location": data.get("location"),
                        "carrier": data.get("carrier"),
                        "line_type": data.get("line_type"),
                        "valid": data.get("valid"),
                    },
                )]
        except Exception:
            return []
