"""
backend/ingestion/photo_enrich.py — profile-photo perceptual-hash enrichment.

Several scrapers return a profile-picture URL (under different keys: photo_url,
avatar, image, ...). The correlation engine can match two accounts by comparing a
perceptual hash (`photo_phash`) with a Hamming distance — but NOTHING populated that
field, so cross-platform photo matching silently degraded to exact-URL equality
(useless: every platform rewrites avatar URLs).

This module downloads each profile photo once, computes an `imagehash.phash`, and
writes it back to `metadata["photo_phash"]` (and normalises the URL into
`metadata["photo_url"]`). That makes the `profile_photo_phash` signal real:
the same face/photo reused across platforms now links the accounts.

Fail-safe: any download/decode error skips that one photo (returns nothing for it);
it never raises. Bounded concurrency + size/time caps so it can't hang a run.
Only meaningful in DATA_MODE=live; the orchestrator guards the call.
"""
from __future__ import annotations

import asyncio
from io import BytesIO

import httpx

# Keys various scrapers use to hold a profile-picture URL, in priority order.
_PHOTO_KEYS = ("photo_url", "avatar", "avatar_url", "image", "image_url",
               "profile_pic", "profile_image", "icon_img")

_MAX_BYTES = 5 * 1024 * 1024          # don't download more than 5 MB per image
_CONCURRENCY = 8                       # parallel downloads cap
_TIMEOUT = 10.0

_PLACEHOLDER_IMAGE_MARKERS = (
    "default_profile_images", "default_profile_normal", "default_profile.png",
    "avatar-default", "no_avatar", "no-avatar", "anonymous-user",
    "missing-avatar", "default-avatar",
)


def _photo_url_of(meta: dict) -> str | None:
    for k in _PHOTO_KEYS:
        v = meta.get(k)
        if isinstance(v, str) and v.startswith("http"):
            url = v.split("?")[0] if k == "icon_img" else v
            if any(marker in url.lower() for marker in _PLACEHOLDER_IMAGE_MARKERS):
                continue
            return url
    return None


async def _hash_one(client: httpx.AsyncClient, sem: asyncio.Semaphore, meta: dict) -> None:
    """Download one profile photo and write metadata['photo_phash']. Never raises."""
    url = _photo_url_of(meta)
    if not url or meta.get("photo_phash"):
        return
    try:
        import imagehash
        from PIL import Image
    except Exception:
        return  # pillow/imagehash unavailable -> signal stays on URL-equality fallback
    try:
        async with sem:
            r = await client.get(url, timeout=_TIMEOUT,
                                 headers={"User-Agent": "VERTEX-OSINT"})
        if r.status_code != 200:
            return
        ctype = r.headers.get("content-type", "")
        if "image" not in ctype:
            return
        content = r.content
        if not content or len(content) > _MAX_BYTES:
            return
        img = Image.open(BytesIO(content)).convert("RGB")
        meta["photo_phash"] = str(imagehash.phash(img))
        # normalise so the URL-equality fallback also has a consistent key
        meta.setdefault("photo_url", url)
    except Exception:
        return


async def enrich_photos(profiles) -> int:
    """Compute photo_phash for every profile that has a photo URL but no hash yet.

    Mutates profile.metadata in place. Returns the count of photos hashed.
    """
    targets = [p.metadata for p in profiles
               if isinstance(getattr(p, "metadata", None), dict)
               and _photo_url_of(p.metadata) and not p.metadata.get("photo_phash")]
    if not targets:
        return 0
    sem = asyncio.Semaphore(_CONCURRENCY)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        await asyncio.gather(*[_hash_one(client, sem, m) for m in targets],
                             return_exceptions=True)
    return sum(1 for m in targets if m.get("photo_phash"))
