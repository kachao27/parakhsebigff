"""L4 Models: signal only, never the verdict alone.

Ships now: URL heuristics (lookalike distance to real broker domains,
suspicious TLDs). Face-manipulation classifier lands in the Aug 2-4 block
as an additional amber signal.
"""
from difflib import SequenceMatcher
from urllib.parse import urlparse

REAL_BROKER_DOMAINS = [
    "zerodha.com", "kite.zerodha.com", "groww.in", "upstox.com",
    "angelone.in", "icicidirect.com", "hdfcsec.com", "kotaksecurities.com",
    "sbisecurities.in", "motilaloswal.com", "5paisa.com", "dhan.co",
    "sebi.gov.in", "nseindia.com", "bseindia.com",
]

SUSPICIOUS_TLDS = (".xyz", ".top", ".online", ".site", ".club", ".vip", ".icu", ".link")


def url_signals(url: str) -> list[str]:
    """Return list of human-readable signal strings (empty = no signal)."""
    signals = []
    if not url.startswith("http"):
        url = "https://" + url
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return signals

    for real in REAL_BROKER_DOMAINS:
        if host == real or host.endswith("." + real):
            return []  # exact legitimate domain
    for real in REAL_BROKER_DOMAINS:
        base = real.split(".")[0]
        host_base = host.replace("www.", "").split(".")[0]
        ratio = SequenceMatcher(None, host_base, base).ratio()
        if 0.7 <= ratio < 1.0 or (base in host_base and host_base != base):
            signals.append(f"looks similar to the real domain {real} but is not it")
            break
    if host.endswith(SUSPICIOUS_TLDS):
        signals.append("uses a low-cost domain extension common in scam sites")
    return signals


def media_signal(path: str, kind: str) -> float | None:
    """CPU face-manipulation heuristic, 0..1. Signal only - never a verdict.

    Method (stated honestly on the card as a signal): detect faces
    (Haar cascade), then compare two artifact measures between the face
    region and the rest of the frame:
      1. sharpness ratio (Laplacian variance) - spliced/generated faces are
         often smoother or sharper than their surroundings;
      2. error-level ratio (recompression residue) - pasted regions
         recompress differently from the rest of the image.
    Returns None when no face is found or analysis fails.
    """
    try:
        import cv2
        import numpy as np

        img = cv2.imread(path)
        if img is None:
            return None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
        if len(faces) == 0:
            return None

        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        face, rest = gray[y:y + h, x:x + w], gray.copy()
        rest[y:y + h, x:x + w] = 0

        def lap_var(a):
            return float(cv2.Laplacian(a, cv2.CV_64F).var()) + 1e-6

        sharp_ratio = lap_var(face) / lap_var(rest)
        sharp_score = min(abs(np.log2(sharp_ratio)) / 3.0, 1.0)  # 8x mismatch -> 1.0

        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        ela = cv2.absdiff(img, cv2.imdecode(enc, cv2.IMREAD_COLOR))
        ela_face = float(ela[y:y + h, x:x + w].mean()) + 1e-6
        ela_rest = float(ela.mean()) + 1e-6
        ela_score = min(abs(np.log2(ela_face / ela_rest)) / 2.0, 1.0)

        return round(0.5 * sharp_score + 0.5 * ela_score, 3)
    except Exception:
        return None
