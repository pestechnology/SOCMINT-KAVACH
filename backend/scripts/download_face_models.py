"""
backend/scripts/download_face_models.py — one-time setup: fetch the two small
pretrained ONNX models used by backend/ingestion/photo_enrich.py for face matching.

Run once after `pip install -r requirements.txt`:

    python backend/scripts/download_face_models.py

Both files are from the official OpenCV Zoo (github.com/opencv/opencv_zoo,
Apache-2.0, redistributable) and are NOT committed to git (see .gitignore) — they're
binary model weights, not source code, and total ~37 MB.

If this script is never run, face matching is simply disabled: photo_enrich.py's
face_matching_available() returns False, metadata["face_embedding"] is never set, and
correlation_engine.py's face_match signal never fires. Every other signal (including
profile_photo_phash) is completely unaffected — this is an additive, optional feature
by design.
"""
from __future__ import annotations

import os
import sys
import urllib.request

_MODELS = {
    "face_detection_yunet.onnx":
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
        "face_detection_yunet_2023mar.onnx",
    "face_recognition_sface.onnx":
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/"
        "face_recognition_sface_2021dec.onnx",
}

_MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")


def main() -> int:
    os.makedirs(_MODEL_DIR, exist_ok=True)
    for filename, url in _MODELS.items():
        dest = os.path.join(_MODEL_DIR, filename)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print(f"[skip] {filename} already present")
            continue
        print(f"[download] {filename} <- {url}")
        try:
            urllib.request.urlretrieve(url, dest)
            print(f"[ok] {filename} ({os.path.getsize(dest):,} bytes)")
        except Exception as e:
            print(f"[FAILED] {filename}: {e}")
            print("Face matching will stay disabled until this file is present "
                  "— every other signal is unaffected.")
            return 1
    print("Face models ready. photo_enrich.face_matching_available() should now be True.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
