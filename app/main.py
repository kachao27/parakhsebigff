"""Parakh - verdict machine for investors, sensor network for the regulator.

Routes:
  GET  /webhook          WhatsApp verification handshake
  POST /webhook          inbound messages (FR1)
  POST /api/check        web checker: text or file (FR2)
  GET  /api/stats        sightings + campaigns for the dashboard (FR6/FR7)
  POST /api/advise/{id}  push advisory to every sender of a campaign artifact (FR7)
  GET  /api/evidence/{id} evidence packet JSON (FR8)
  GET  /                 web checker page
  GET  /health           ops
"""
import json
import logging
import os
import time

from fastapi import FastAPI, Request, Response, UploadFile, Form, File
from fastapi.responses import FileResponse, JSONResponse

from . import cards, ocr, wa
from .config import settings
from .db import init_db, get_db, record_sighting, senders_of
from .engine import verdict as check_engine
from .engine.verdict import check_text, check_media
from .router import classify_text, detect_lang

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("parakh")

app = FastAPI(title="Parakh")


@app.on_event("startup")
def startup():
    os.makedirs(os.path.dirname(settings.database_path) or ".", exist_ok=True)
    init_db()


@app.get("/health")
def health():
    return {"ok": True, "ts": time.time()}


@app.get("/")
def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "web", "index.html"))


@app.get("/dashboard")
def dashboard():
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "web", "dashboard.html"))


# ---------------- FR1: WhatsApp webhook ----------------

@app.get("/webhook")
def verify(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == settings.wa_verify_token:
        return Response(content=q.get("hub.challenge", ""), media_type="text/plain")
    return Response(status_code=403)


_seen_msg_ids: set[str] = set()


@app.post("/webhook")
async def receive(request: Request):
    """Acknowledge Meta INSTANTLY (it retries if we don't 200 within ~20s), then
    process each message in a background thread. Dedupe by message id so a retry
    that races our ack never double-processes."""
    body = await request.json()
    import threading

    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []):
                mid = msg.get("id", "")
                if mid and mid in _seen_msg_ids:
                    continue
                if mid:
                    _seen_msg_ids.add(mid)
                    if len(_seen_msg_ids) > 2000:
                        _seen_msg_ids.clear()
                threading.Thread(target=_safe_handle, args=(msg,), daemon=True).start()
    return {"status": "ok"}


def _safe_handle(msg: dict):
    try:
        _handle_message(msg)
    except Exception:
        log.exception("webhook handling failed")


def _handle_message(msg: dict):
    sender = msg.get("from")
    mtype = msg.get("type")
    verdict = None

    if mtype == "text":
        body = msg["text"]["body"].strip()
        from .linkmeta import is_video_link
        if is_video_link(body):
            verdict = check_engine.check_link(body, lang=detect_lang(body))
        else:
            verdict = check_text(classify_text(body))

    elif mtype in ("image", "video"):
        ack = {"video": "🔎 Reading your video - content, spoken words and any known-fake match. One moment…",
               "image": "🔎 Reading your screenshot…"}[mtype]
        wa.send_text(sender, ack)
        suffix = ".jpg" if mtype == "image" else ".mp4"
        path = wa.download_media(msg[mtype]["id"], suffix)
        try:
            caption = msg[mtype].get("caption", "")
            text = ocr.extract_text(path) if mtype == "image" else ""
            combined = (caption + "\n" + text).strip()
            verdict = check_media(path, mtype, ocr_text=combined, lang=detect_lang(combined))
        finally:
            os.unlink(path)  # media never kept at rest

    elif mtype == "audio":
        wa.send_text(sender, "🔎 Listening to your voice note…")
        path = wa.download_media(msg["audio"]["id"], ".ogg")
        try:
            verdict = check_media(path, "audio", lang="en")
        except Exception:
            log.exception("audio check failed")
            verdict = None
        finally:
            os.unlink(path)
        if verdict is None:
            wa.send_text(sender, "🟡 Could not analyse this voice note. Forward the text of the offer and I will check it now.")
            return

    elif mtype == "contacts":
        phones = [p.get("phone", "") for c in msg.get("contacts", []) for p in c.get("phones", [])]
        if phones:
            verdict = check_text(classify_text(phones[0]))

    elif mtype == "interactive":
        _handle_button(sender, msg["interactive"])
        return

    if verdict is None:
        wa.send_text(sender, "Forward a message, number, screenshot, video or UPI ID and I will check it against SEBI's registry and rules.")
        return

    record_sighting(verdict.artifact_hash, verdict.artifact_kind, verdict.color,
                    verdict.ref_id, "whatsapp", sender)
    wa.send_buttons(sender, cards.render_text(verdict), cards.buttons_for(verdict))

    # Advice verdict with an identity: run the slow OSINT web check out-of-band
    # and send a follow-up, so the primary card is never blocked on it.
    if getattr(verdict, "pending_name", ""):
        import threading

        def _followup(name, handles, to):
            try:
                fu = check_engine.enrich_identity(name, handles)
                wa.send_text(to, f"*{fu['title']}*\n\n{fu['text']}")
            except Exception:
                log.exception("osint follow-up failed")

        threading.Thread(target=_followup,
                         args=(verdict.pending_name, verdict.pending_handles, sender),
                         daemon=True).start()


def _handle_button(sender: str, interactive: dict):
    reply = interactive.get("button_reply", {})
    bid = reply.get("id")
    if bid == "report":
        wa.send_text(sender, "✅ Reported to SEBI with the evidence packet. "
                             "You will be notified if your report contributes to an advisory.")
    elif bid == "advisory":
        wa.send_text(sender, "📄 Advisory: this content matches a confirmed fake on record. "
                             "Do not act on it, and warn anyone who forwarded it to you.")
    elif bid == "block":
        wa.send_text(sender, "To block: open the sender's chat → tap their name → Block. "
                             "Reporting them to WhatsApp also helps takedowns.")


# ---------------- FR2: web checker ----------------

@app.post("/api/check")
async def api_check(text: str = Form(None), file: UploadFile = File(None)):
    if file is not None:
        suffix = os.path.splitext(file.filename or "")[1] or ".bin"
        import tempfile
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(await file.read())
        tmp.close()
        try:
            kind = "video" if suffix.lower() in (".mp4", ".mov", ".avi", ".mkv", ".webm") else "image"
            extracted = ocr.extract_text(tmp.name) if kind == "image" else ""
            verdict = check_media(tmp.name, kind, ocr_text=extracted, lang=detect_lang(extracted))
        finally:
            os.unlink(tmp.name)
    elif text:
        from .linkmeta import is_video_link
        t = text.strip()
        verdict = (check_engine.check_link(t, lang=detect_lang(t))
                   if is_video_link(t) else check_text(classify_text(t)))
    else:
        return JSONResponse({"error": "provide text or file"}, status_code=400)

    record_sighting(verdict.artifact_hash, verdict.artifact_kind, verdict.color,
                    verdict.ref_id, "web")
    out = cards.to_json(verdict)
    out["pending_name"] = getattr(verdict, "pending_name", "")
    out["pending_handles"] = getattr(verdict, "pending_handles", [])
    return out


@app.get("/api/deepcheck")
def api_deepcheck(name: str, handles: str = ""):
    """Slow OSINT web check for an identified advice-giver (web-checker follow-up)."""
    hl = [h for h in handles.split(",") if h.strip()]
    return check_engine.enrich_identity(name, hl)


# ---------------- FR6/FR7/FR8: regulator view ----------------

@app.get("/api/stats")
def api_stats():
    since = time.time() - 24 * 3600
    with get_db() as db:
        totals = db.execute(
            "SELECT verdict, COUNT(*) c FROM sightings GROUP BY verdict").fetchall()
        recent = db.execute(
            "SELECT artifact_hash, kind, verdict, ref_id, ts, channel FROM sightings"
            " ORDER BY ts DESC LIMIT 50").fetchall()
        camps = db.execute(
            "SELECT * FROM campaigns ORDER BY count DESC").fetchall()
        series = db.execute(
            "SELECT ts, verdict, kind FROM sightings WHERE ts>? ORDER BY ts", (since,)).fetchall()
        kinds = db.execute(
            "SELECT kind, COUNT(*) c FROM sightings GROUP BY kind ORDER BY c DESC").fetchall()
        protected = db.execute(
            "SELECT COUNT(DISTINCT sender) c FROM sightings WHERE sender IS NOT NULL").fetchone()
        reg_total = db.execute("SELECT COUNT(*) c FROM registries").fetchone()
        camp_series = {c["hash"]: [r["ts"] for r in db.execute(
            "SELECT ts FROM sightings WHERE artifact_hash=? AND ts>? ORDER BY ts",
            (c["hash"], since))] for c in camps}
    camp_list = []
    for c in camps:
        d = dict(c)
        if d.get("intel"):
            try:
                d["intel"] = json.loads(d["intel"])
            except Exception:
                d["intel"] = None
        camp_list.append(d)
    return {
        "totals": {r["verdict"]: r["c"] for r in totals},
        "recent": [dict(r) for r in recent],
        "campaigns": camp_list,
        "series": [dict(r) for r in series],
        "kinds": [dict(r) for r in kinds],
        "protected": protected["c"],
        "registry_rows": reg_total["c"],
        "campaign_series": camp_series,
    }


@app.post("/api/campaign/{campaign_id}/intel")
def api_campaign_intel(campaign_id: int, refresh: bool = False):
    """Generate (and cache) an AI intelligence brief for a campaign."""
    with get_db() as db:
        camp = db.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
        if camp is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        if camp["intel"] and not refresh:
            return json.loads(camp["intel"])
        timeline = [dict(r) for r in db.execute(
            "SELECT ts, verdict, channel, kind FROM sightings WHERE artifact_hash=? ORDER BY ts",
            (camp["hash"],)).fetchall()]
    intel = check_engine.campaign_intel.generate(dict(camp), timeline)
    if intel is None:
        return JSONResponse({"error": "intel unavailable"}, status_code=503)
    with get_db() as db:
        db.execute("UPDATE campaigns SET intel=? WHERE id=?", (json.dumps(intel), campaign_id))
    return intel


@app.post("/api/advise/{campaign_id}")
def api_advise(campaign_id: int):
    """FR7: push advisory to every sender of the campaign artifact."""
    with get_db() as db:
        camp = db.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
        if camp is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        advisory = camp["advisory_text"] or (
            "⚠️ *SEBI-linked advisory (Parakh)*\n\n"
            "Content you checked recently is part of an active scam campaign "
            f"({camp['count']} sightings). Do not act on it. "
            "Your report contributed to this advisory. Advisory ref PA-%03d." % camp["id"]
        )
        db.execute("UPDATE campaigns SET status='advised', advisory_text=? WHERE id=?",
                   (advisory, campaign_id))
    recipients = senders_of(camp["hash"])
    for r in recipients:
        wa.send_text(r, advisory)
    return {"advised": len(recipients), "status": "advised"}


@app.get("/api/evidence/{campaign_id}")
def api_evidence(campaign_id: int):
    """FR8: evidence packet JSON."""
    with get_db() as db:
        camp = db.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
        if camp is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        sights = db.execute(
            "SELECT kind, verdict, ref_id, ts, channel FROM sightings WHERE artifact_hash=? ORDER BY ts",
            (camp["hash"],)).fetchall()
    packet = {
        "packet": f"PA-{camp['id']:03d}",
        "artifact_hash": camp["hash"],
        "kind": camp["kind"],
        "first_seen": camp["first_seen"],
        "count": camp["count"],
        "status": camp["status"],
        "sample_verdict": camp["sample_verdict"],
        "advisory_text": camp["advisory_text"],
        "timeline": [dict(s) for s in sights],
        "note": "No message content is stored; hashes and verdict metadata only (DPDP).",
    }
    return Response(content=json.dumps(packet, indent=2),
                    media_type="application/json",
                    headers={"Content-Disposition": f"attachment; filename=evidence_PA-{camp['id']:03d}.json"})
