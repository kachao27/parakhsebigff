"""Register a media file as a confirmed fake in the fingerprint registry.

Usage: python scripts/fingerprint_media.py <path> "<label>" [advisory_ref]

Used before the demo to fingerprint our own clearly-labelled synthetic clip
(a fictional exchange official — no real person is faked). Every keyframe is
hashed at three center crops so cropped/re-encoded copies still match.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import init_db  # noqa: E402
from app.engine import l3_memory  # noqa: E402

if __name__ == "__main__":
    path, label = sys.argv[1], sys.argv[2]
    ref = sys.argv[3] if len(sys.argv) > 3 else "PA-001 demo advisory"
    lower = path.lower()
    if lower.endswith((".mp4", ".mov", ".mkv", ".webm", ".avi")):
        kind, hasher = "video", l3_memory.video_hashes
    elif lower.endswith((".ogg", ".mp3", ".m4a", ".aac", ".wav", ".opus")):
        kind, hasher = "audio", l3_memory.audio_hashes
    else:
        kind, hasher = "image", l3_memory.image_hashes
    init_db()
    hashes = hasher(path)
    l3_memory.register_fingerprint(hashes, kind, label, ref)
    print(f"registered {len(hashes)} hashes for {kind}: {label}")
