"""
backend/ingestion/photo_enrich.py — profile-photo perceptual-hash + face-embedding
enrichment.

Several scrapers return a profile-picture URL (under different keys: photo_url,
avatar, image, ...). This module downloads each profile photo once and computes TWO
independent, complementary signals from it:

  1. `photo_phash` (imagehash.phash) — catches the SAME IMAGE FILE reused across
     platforms (e.g. the identical avatar upload). Cheap, exact-ish, but blind to
     "same person, different photo" — the common real-world case.
  2. `face_embedding` (128-d SFace vector, see FACE MATCHING below) — catches the
     SAME PERSON even in a different photo, by comparing facial biometrics.

Both are independent hard-anchor signals in correlation_engine.py; they fire on
different evidence and are not redundant (see that module's docstring).

FACE MATCHING — model choice and why:
  `face_recognition` (the usual Python face-rec library) requires `dlib`, which has
  no prebuilt wheel for this Python/Windows combination and must be compiled from
  source with CMake + a C++ toolchain — neither is available in this environment
  (confirmed: `pip install --dry-run dlib` resolves only a source sdist, and no
  `cmake`/`cl.exe` is on PATH). That is the exact build failure this project already
  hit with scikit-learn.

  Instead this uses OpenCV's official, pretrained ONNX models from the OpenCV Zoo
  (github.com/opencv/opencv_zoo — Apache-2.0, redistributable):
    - face_detection_yunet (YuNet, ~230 KB)   — detects + aligns faces
    - face_recognition_sface (SFace, ~37 MB)  — 128-d face embedding
  `opencv-python-headless` is a pure-wheel install on Windows (no C++ toolchain, no
  GUI deps) and both models load through cv2's own `dnn` module — zero extra Python
  dependencies beyond OpenCV, which the project already uses.

  SFace is a peer-reviewed face-recognition model (Zhong et al., "SFace:
  Sigmoid-Constrained Hypersphere Loss for Robust Face Recognition", IEEE TIP 2021)
  achieving 99.60% accuracy on the LFW same/different-person benchmark. OpenCV's own
  `FaceRecognizerSF.match()` API ships a calibrated decision threshold for exactly
  this same/different-person question: cosine similarity >= 0.363 = same person
  (OpenCV Zoo's documented default for `FaceRecognizerSF_FR_COSINE`). We use that
  published threshold rather than guessing one — see `_FACE_COSINE_THRESHOLD` below.

  Model files are NOT committed to git (large binaries) — see
  `backend/scripts/download_face_models.py` / SETUP.md. If they are absent, or if
  no face is detected in a photo (logo, group photo, meme), `face_embedding` is
  simply left unset — it is never a fallback-hashed whole image pretending to be a
  face. The pipeline runs identically with or without the models present.

Fail-safe: any download/decode/model error skips that one photo; it never raises.
Bounded concurrency + size/time caps so it can't hang a run. Only meaningful in
DATA_MODE=live; the orchestrator guards the call.
"""
from __future__ import annotations

import asyncio
import os
from io import BytesIO

import httpx

from backend.ingestion.base_module import RawProfile, make_profile

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

# ---------------------------------------------------------------------------
# Face detection / embedding (OpenCV Zoo YuNet + SFace — see module docstring)
# ---------------------------------------------------------------------------
_MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
_DETECTOR_PATH = os.path.join(_MODEL_DIR, "face_detection_yunet.onnx")
_RECOGNIZER_PATH = os.path.join(_MODEL_DIR, "face_recognition_sface.onnx")

# OpenCV Zoo's own documented decision threshold for FaceRecognizerSF_FR_COSINE
# (>= this cosine similarity = same person). Shared with correlation_engine.py's
# face_match signal so detection and correlation agree on what "same person" means.
FACE_COSINE_THRESHOLD = 0.363
_FACE_EMBED_DIM = 128

_face_models_cache: dict = {}


def _face_models():
    """Lazily load (detector, recognizer), cached process-wide. (None, None) if the
    model files are missing or cv2 isn't installed — callers treat that as 'feature
    unavailable', never as an error."""
    if "loaded" in _face_models_cache:
        return _face_models_cache["detector"], _face_models_cache["recognizer"]
    _face_models_cache["loaded"] = True
    _face_models_cache["detector"] = None
    _face_models_cache["recognizer"] = None
    if not (os.path.exists(_DETECTOR_PATH) and os.path.exists(_RECOGNIZER_PATH)):
        return None, None
    try:
        import cv2
        det = cv2.FaceDetectorYN.create(_DETECTOR_PATH, "", (320, 320),
                                        score_threshold=0.8)
        rec = cv2.FaceRecognizerSF.create(_RECOGNIZER_PATH, "")
        _face_models_cache["detector"] = det
        _face_models_cache["recognizer"] = rec
    except Exception:
        pass
    return _face_models_cache["detector"], _face_models_cache["recognizer"]


def face_matching_available() -> bool:
    """True if both ONNX models are present and loadable. Used by tests/health checks."""
    det, rec = _face_models()
    return det is not None and rec is not None


def extract_face_embedding_from_bytes(content: bytes) -> list[float] | None:
    """Detect the most prominent face in an image and return its 128-d SFace
    embedding, or None if no face is detected / models are unavailable / decoding
    fails. Never raises. If MULTIPLE faces are present (group photo), uses the
    largest bounding box — profile photos are overwhelmingly single-subject, and a
    largest-face heuristic avoids picking a stranger in the background."""
    det, rec = _face_models()
    if det is None or rec is None:
        return None
    try:
        import cv2
        import numpy as np
        arr = np.frombuffer(content, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        h, w = img.shape[:2]
        if h < 20 or w < 20:
            return None
        det.setInputSize((w, h))
        status, faces = det.detect(img)
        if faces is None or len(faces) == 0:
            return None
        # faces[i] = [x, y, w, h, <5 landmark pairs>, score]; pick the largest box.
        largest = max(faces, key=lambda f: f[2] * f[3])
        aligned = rec.alignCrop(img, largest)
        feature = rec.feature(aligned)
        return [round(float(x), 6) for x in feature.flatten().tolist()]
    except Exception:
        return None


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
    """Download one profile photo and write photo_phash + (if a face is found)
    face_embedding. Never raises."""
    url = _photo_url_of(meta)
    if not url or (meta.get("photo_phash") and "face_embedding" in meta):
        return
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
    except Exception:
        return

    if not meta.get("photo_phash"):
        try:
            import imagehash
            from PIL import Image
            img = Image.open(BytesIO(content)).convert("RGB")
            meta["photo_phash"] = str(imagehash.phash(img))
            # normalise so the URL-equality fallback also has a consistent key
            meta.setdefault("photo_url", url)
        except Exception:
            pass  # pillow/imagehash unavailable -> signal stays on URL-equality fallback

    if "face_embedding" not in meta:
        emb = extract_face_embedding_from_bytes(content)
        if emb is not None:
            meta["face_embedding"] = emb
        # No face detected -> leave face_embedding unset entirely (never a
        # whole-image fallback masquerading as a face signal).


async def enrich_photos(profiles) -> int:
    """Compute photo_phash + face_embedding for every profile that has a photo URL.

    Mutates profile.metadata in place. Returns the count of photos processed
    (hashed and/or face-embedded).
    """
    targets = [p.metadata for p in profiles
               if isinstance(getattr(p, "metadata", None), dict)
               and _photo_url_of(p.metadata)
               and not (p.metadata.get("photo_phash") and "face_embedding" in p.metadata)]
    if not targets:
        return 0
    sem = asyncio.Semaphore(_CONCURRENCY)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        await asyncio.gather(*[_hash_one(client, sem, m) for m in targets],
                             return_exceptions=True)
    return sum(1 for m in targets if m.get("photo_phash") or m.get("face_embedding"))


async def build_face_seed_profile(image_url: str) -> RawProfile | None:
    """For a 'face' seed (investigator-supplied reference photo URL): download it,
    extract its face embedding, and return it as a normal RawProfile so the existing
    correlate()/score() pipeline compares it against every other discovered profile
    with zero special-casing (same pattern as any other seed-derived profile).

    Returns None (never raises) if the URL can't be fetched, isn't an image, or has
    no detectable face — the investigation simply proceeds without a face seed.
    """
    if not image_url or not str(image_url).startswith("http"):
        return None
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.get(image_url, timeout=_TIMEOUT,
                                 headers={"User-Agent": "VERTEX-OSINT"})
        if r.status_code != 200 or "image" not in r.headers.get("content-type", ""):
            return None
        content = r.content
        if not content or len(content) > _MAX_BYTES:
            return None
        emb = extract_face_embedding_from_bytes(content)
        if emb is None:
            return None
        return make_profile(
            "face", image_url, "seed_photo", image_url,
            metadata={"face_embedding": emb, "photo_url": image_url,
                     "note": "Investigator-supplied reference photo"},
        )
    except Exception:
        return None
