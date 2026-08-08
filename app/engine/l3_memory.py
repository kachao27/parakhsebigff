"""L3 Memory: fingerprint match for media, blacklist for numbers/URLs/UPIs.

Crop + re-encode robustness: at index time every keyframe is hashed at three
center crops (100%, 80%, 60%); at query time each keyframe hash is compared
against all stored variants. Match = Hamming distance <= threshold (default
10 of 64 bits, documented in config).
"""
import subprocess
import tempfile
import time
from pathlib import Path

import imagehash
from PIL import Image

from ..config import settings
from ..db import get_db

CROPS = (1.0, 0.8, 0.6)


def _center_crop(img: Image.Image, ratio: float) -> Image.Image:
    if ratio >= 1.0:
        return img
    w, h = img.size
    cw, ch = int(w * ratio), int(h * ratio)
    left, top = (w - cw) // 2, (h - ch) // 2
    return img.crop((left, top, left + cw, top + ch))


def image_hashes(path: str) -> list[str]:
    img = Image.open(path).convert("RGB")
    return [str(imagehash.phash(_center_crop(img, r))) for r in CROPS]


def video_keyframes(path: str, max_frames: int = 8) -> list[str]:
    """Extract evenly spaced frames via ffmpeg; return frame image paths."""
    out = tempfile.mkdtemp(prefix="parakh_kf_")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", path,
         "-vf", f"fps=1,select='not(mod(n\\,2))'", "-frames:v", str(max_frames),
         f"{out}/f%03d.jpg"],
        check=True, timeout=60,
    )
    return sorted(str(p) for p in Path(out).glob("*.jpg"))


def video_hashes(path: str) -> list[str]:
    hashes = []
    for frame in video_keyframes(path):
        hashes.extend(image_hashes(frame))
    return hashes


def audio_hashes(path: str) -> list[str]:
    """Best-effort audio fingerprint: render a spectrogram via ffmpeg, pHash
    it at three time-axis crops (100/90/80% centered) - codecs pad and shift
    the start (mp3 encoder delay), so time-shifted copies still land within
    threshold. Survives re-encoding and container swaps; weak against heavy
    trimming (documented limitation)."""
    out = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", path,
         "-lavfi", "showspectrumpic=s=512x256:legend=0:scale=log", out],
        check=True, timeout=60,
    )
    img = Image.open(out).convert("RGB")
    w, h = img.size
    hashes = []
    for ratio in (1.0, 0.9, 0.8):
        cw = int(w * ratio)
        left = (w - cw) // 2
        hashes.append(str(imagehash.phash(img.crop((left, 0, left + cw, h)))))
    return hashes


def _hamming(h1: str, h2: str) -> int:
    return bin(int(h1, 16) ^ int(h2, 16)).count("1")


def match_fingerprint(query_hashes: list[str], kind: str):
    """Return (fingerprint_row, distance) of best match under threshold, else None."""
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM fingerprints WHERE kind IN (?, 'image', 'video')", (kind,)
        ).fetchall()
    best, best_d = None, 65
    for row in rows:
        for qh in query_hashes:
            d = _hamming(qh, row["hash"])
            if d < best_d:
                best, best_d = row, d
    if best is not None and best_d <= settings.phash_hamming_threshold:
        return best, best_d
    return None


def register_fingerprint(hashes: list[str], kind: str, label: str, advisory_ref: str | None):
    with get_db() as db:
        for h in hashes:
            db.execute(
                "INSERT INTO fingerprints (hash, kind, label, advisory_ref, first_seen)"
                " VALUES (?,?,?,?,?)",
                (h, kind, label, advisory_ref, time.time()),
            )


def blacklist_lookup(kind: str, value: str):
    v = value.lower().strip()
    if kind == "phone":
        v = v[-10:]
    with get_db() as db:
        return db.execute(
            "SELECT * FROM blacklist WHERE kind=? AND value=?", (kind, v)
        ).fetchone()
