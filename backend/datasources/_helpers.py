"""Shared helper utilities for data sources."""

import asyncio
import io
import logging
import re
from typing import Optional

import httpx
import imagehash
from PIL import Image

from backend.schemas import RawProfile


def normalize_phone(raw: str) -> str:
    """Normalize raw phone string to E.164 format (defaulting to +91 for 10-digit Indian numbers)."""
    cleaned = re.sub(r"[\s\-\(\)\.]", "", raw)
    if cleaned.startswith("+"):
        return cleaned
    cleaned = cleaned.lstrip("0")
    if len(cleaned) == 10:
        return f"+91{cleaned}"
    return f"+{cleaned}"



async def fetch_and_phash_photos(
    profiles: list[RawProfile], logger: Optional[logging.Logger] = None
) -> None:
    """
    For each profile in the list, if metadata['photo_url'] is non-empty,
    fetch the image in parallel and store the hex phash in metadata['photo_phash'].
    Failures are logged but don't raise. Mutates profiles in place.
    """
    log = logger or logging.getLogger(__name__)

    stats = {
        "succeeded": 0,
        "failed": 0,
        "timeout": 0,
        "decode": 0,
        "http": 0,
    }

    async def _fetch_and_hash_photo(client: httpx.AsyncClient, p: RawProfile) -> None:
        url = p.metadata.get("photo_url", "")
        if not url:
            return
        try:
            resp = await client.get(url, timeout=5.0, follow_redirects=True)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content))
            ph = str(imagehash.phash(img))
            p.metadata["photo_phash"] = ph
            stats["succeeded"] += 1
        except Exception as e:
            stats["failed"] += 1
            exc_type = type(e).__name__
            log.warning("photo fetch failed URL=%s type=%s message=%s", url, exc_type, str(e))
            if isinstance(e, (httpx.TimeoutException, asyncio.TimeoutError)):
                stats["timeout"] += 1
            elif isinstance(e, httpx.HTTPError):
                stats["http"] += 1
            else:
                stats["decode"] += 1

    if not profiles:
        return

    async with httpx.AsyncClient() as client:
        await asyncio.gather(*[_fetch_and_hash_photo(client, p) for p in profiles])

    log.info(
        "Photo pHash: succeeded %d, failed %d (timeout: %d, decode error: %d, http error: %d)",
        stats["succeeded"], stats["failed"], stats["timeout"], stats["decode"], stats["http"]
    )
