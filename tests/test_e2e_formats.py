"""End-to-end format matrix. Every artifact type PRD FR3 names, through the
real pipeline: FastAPI app -> router -> engine -> card.

- /api/check covers the web path for text/image/video/audio.
- /webhook covers the WhatsApp path with real Meta payload shapes; outbound
  send + media download are monkeypatched (the live transport was proven on a
  real phone), so what's tested here is parsing, routing, verdicts, cards.

Runs on a COPY of the real DB (8k+ scraped registry rows + seeds); test
fingerprints never pollute the live store.

Run: PATH=/opt/homebrew/bin:$PATH .venv/bin/python -m pytest tests/test_e2e_formats.py -q
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402


@pytest.fixture(scope="session")
def media(tmp_path_factory):
    """Generate one of every media format with ffmpeg/PIL."""
    d = tmp_path_factory.mktemp("media")
    ff = ["ffmpeg", "-y", "-loglevel", "error"]
    # video + its adversarial copy
    subprocess.run([*ff, "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=4",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(d / "fake.mp4")], check=True)
    subprocess.run([*ff, "-i", str(d / "fake.mp4"), "-vf", "crop=iw*0.75:ih*0.75,scale=480:270",
                    "-c:v", "libx264", "-b:v", "150k", "-pix_fmt", "yuv420p",
                    str(d / "fake_cropped.mp4")], check=True)
    subprocess.run([*ff, "-f", "lavfi", "-i", "smptebars=size=640x360:rate=25:duration=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(d / "clean.mp4")], check=True)
    # audio: voice-like modulated signal (a pure sine has a near-empty
    # spectrogram and is not representative of voice notes) + re-encode
    subprocess.run([*ff, "-f", "lavfi", "-i",
                    "aevalsrc=0.4*sin(2*PI*(300+150*sin(2*PI*1.3*t))*t)"
                    "+0.2*sin(2*PI*(800+300*sin(2*PI*0.7*t))*t):d=5",
                    "-ac", "1", str(d / "fake.wav")], check=True)
    subprocess.run([*ff, "-i", str(d / "fake.wav"), "-b:a", "24k", str(d / "fake_reenc.mp3")], check=True)
    subprocess.run([*ff, "-f", "lavfi", "-i", "anoisesrc=d=4:c=pink",
                    "-ac", "1", str(d / "clean.ogg")], check=True)
    # scam screenshot (OCR path) + clean photo
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (900, 400), "white")
    dr = ImageDraw.Draw(img)
    dr.text((30, 80), "JOIN VIP GROUP", fill="black", font_size=48)
    dr.text((30, 160), "SEBI registered tips", fill="black", font_size=40)
    dr.text((30, 240), "3% weekly GUARANTEED returns", fill="black", font_size=40)
    img.save(d / "scam_screenshot.png")
    Image.new("RGB", (600, 400), (90, 140, 200)).save(d / "clean.png")
    return d


@pytest.fixture(scope="session")
def client(media, tmp_path_factory):
    """App on a copy of the real DB, with fingerprints for the fake media."""
    dbcopy = tmp_path_factory.mktemp("db") / "parakh.db"
    shutil.copy(ROOT / "data" / "parakh.db", dbcopy)
    settings.database_path = str(dbcopy)

    from app.engine import l3_memory
    l3_memory.register_fingerprint(l3_memory.video_hashes(str(media / "fake.mp4")),
                                   "video", "Known fake video (test)", "PA-T01")
    l3_memory.register_fingerprint(l3_memory.audio_hashes(str(media / "fake.wav")),
                                   "audio", "Known fake voice note (test)", "PA-T02")

    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def check(client, **form):
    files = None
    if "file" in form:
        p = form.pop("file")
        files = {"file": (p.name, p.open("rb"))}
    r = client.post("/api/check", data=form or None, files=files)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- text formats ----------------

TEXT_CASES = [
    ("pitch_en", "Join VIP group. SEBI registered tips. 3% weekly guaranteed.", "red", "ILLEGAL OFFER"),
    ("pitch_hi", "VIP ग्रुप जॉइन करें। गारंटीड 5% साप्ताहिक रिटर्न।", "red", "ILLEGAL OFFER"),
    ("reg_no_real", "INH000000016", "green", "SEBI REGISTERED"),          # real scraped RA
    ("reg_no_unknown", "INH999999999", "amber", None),
    ("name_real", "Stakeholders Empowerment Services", "green", "SEBI REGISTERED"),
    ("name_unknown", "Totally Unknown Advisory", "amber", None),
    ("phone_seeded", "+91 98765 43210", "green", "SEBI REGISTERED"),
    ("phone_unknown", "9123456780", "amber", None),
    ("upi_blacklisted", "scampay@ybl", "red", "MATCHED KNOWN FAKE"),
    ("upi_unknown", "someone@oksbi", "amber", None),
    ("url_lookalike", "zerodha-kite.xyz", "amber", None),
    ("debarred", "Golden Bull Research", "red", "DEBARRED ENTITY"),
]


@pytest.mark.parametrize("label,text,color,title", TEXT_CASES, ids=[c[0] for c in TEXT_CASES])
def test_text_formats(client, label, text, color, title):
    v = check(client, text=text)
    assert v["color"] == color, v
    if title:
        assert v["title"] == title, v
    if color == "red":
        assert v["citation"], "red verdict must carry a citation"
        assert v["layer"], "red verdict must name its layer"


def test_phone_unknown_exact_phrasing(client):
    v = check(client, text="9123456780")
    assert "No registered entity is publicly associated with this number." in v["reasons"]


# ---------------- media formats ----------------

def test_image_scam_screenshot_ocr(client, media):
    v = check(client, file=media / "scam_screenshot.png")
    assert v["color"] == "red" and v["title"] == "ILLEGAL OFFER", v


def test_image_clean(client, media):
    v = check(client, file=media / "clean.png")
    assert v["color"] == "amber", v


def test_video_fingerprinted(client, media):
    v = check(client, file=media / "fake.mp4")
    assert v["color"] == "red" and v["title"] == "CONFIRMED FAKE", v


def test_video_cropped_reencoded_still_matches(client, media):
    v = check(client, file=media / "fake_cropped.mp4")
    assert v["color"] == "red" and v["title"] == "CONFIRMED FAKE", v


def test_video_clean(client, media):
    v = check(client, file=media / "clean.mp4")
    assert v["color"] == "amber", v


# ---------------- WhatsApp webhook path (real Meta payload shapes) ----------------

def wa_payload(msg):
    return {"entry": [{"changes": [{"value": {"messages": [msg]}}]}]}


def deliver(msg):
    """Call the handler synchronously (the /webhook route now processes in a
    background thread, so we bypass it to make assertions deterministic)."""
    from app import main
    main._handle_message(msg)


def verdict_msg(outbox):
    """The verdict is the last message sent (media sends a '🔎 …' ack first)."""
    return outbox[-1]


@pytest.fixture()
def outbox(monkeypatch):
    sent = []
    from app import main
    monkeypatch.setattr(main.wa, "send_text", lambda to, body: sent.append(("text", to, body)))
    monkeypatch.setattr(main.wa, "send_buttons",
                        lambda to, body, buttons: sent.append(("buttons", to, body, buttons)))
    return sent


def test_webhook_text_red(client, outbox):
    deliver((
        {"from": "919999900001", "type": "text",
         "text": {"body": "Guaranteed 3% weekly returns, joining fee 999"}}))
    kind, to, body, buttons = verdict_msg(outbox)
    assert kind == "buttons" and "ILLEGAL OFFER" in body and "🔴" in body
    assert any(b["id"] == "report" for b in buttons)


def test_webhook_hindi_card(client, outbox):
    deliver((
        {"from": "919999900001", "type": "text",
         "text": {"body": "गारंटीड रिटर्न 5% साप्ताहिक"}}))
    body = verdict_msg(outbox)[2]
    assert "गैरकानूनी ऑफर" in body  # Hindi title


def test_webhook_image_message(client, outbox, media, monkeypatch):
    from app import main
    import shutil as sh, tempfile, os
    def fake_download(media_id, suffix=""):
        t = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        t.close()
        sh.copy(media / "scam_screenshot.png", t.name)
        return t.name
    monkeypatch.setattr(main.wa, "download_media", fake_download)
    deliver((
        {"from": "919999900001", "type": "image", "image": {"id": "MEDIA1", "caption": ""}}))
    assert "ILLEGAL OFFER" in verdict_msg(outbox)[2]


def test_webhook_video_message(client, outbox, media, monkeypatch):
    from app import main
    import shutil as sh, tempfile
    def fake_download(media_id, suffix=""):
        t = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        t.close()
        sh.copy(media / "fake_cropped.mp4", t.name)
        return t.name
    monkeypatch.setattr(main.wa, "download_media", fake_download)
    deliver((
        {"from": "919999900001", "type": "video", "video": {"id": "MEDIA2"}}))
    assert "CONFIRMED FAKE" in verdict_msg(outbox)[2]


def test_webhook_audio_message(client, outbox, media, monkeypatch):
    from app import main
    import shutil as sh, tempfile
    def fake_download(media_id, suffix=""):
        t = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        t.close()
        sh.copy(media / "fake_reenc.mp3", t.name)
        return t.name
    monkeypatch.setattr(main.wa, "download_media", fake_download)
    deliver((
        {"from": "919999900001", "type": "audio", "audio": {"id": "MEDIA3"}}))
    assert "CONFIRMED FAKE" in verdict_msg(outbox)[2]


def test_webhook_contact_card(client, outbox):
    deliver((
        {"from": "919999900001", "type": "contacts",
         "contacts": [{"phones": [{"phone": "+91 98765 43210"}]}]}))
    assert "SEBI REGISTERED" in verdict_msg(outbox)[2]


def test_webhook_button_reply(client, outbox):
    deliver((
        {"from": "919999900001", "type": "interactive",
         "interactive": {"type": "button_reply", "button_reply": {"id": "report", "title": "Report to SEBI"}}}))
    assert "Reported to SEBI" in verdict_msg(outbox)[2]


def test_sightings_recorded_and_campaign_forms(client, outbox):
    for _ in range(3):
        deliver((
            {"from": "919999900002", "type": "text",
             "text": {"body": "Pay withdrawal tax to release your profit now"}}))
    stats = client.get("/api/stats").json()
    assert stats["totals"].get("red", 0) >= 3
    assert any(c["count"] >= 3 for c in stats["campaigns"]), "campaign should cluster"
