"""WhatsApp Cloud API client (official Graph API, test-number tier).

Setup: developers.facebook.com > app > WhatsApp > API Setup gives you the
temporary token + phone_number_id. Webhook URL is {BASE_URL}/webhook with
the verify token from .env. Test tier allows up to 5 recipient numbers.
"""
import logging
import tempfile

import httpx

from .config import settings

log = logging.getLogger("parakh.wa")
GRAPH = "https://graph.facebook.com/v21.0"


def _headers():
    return {"Authorization": f"Bearer {settings.wa_token}"}


def send_text(to: str, body: str):
    r = httpx.post(
        f"{GRAPH}/{settings.wa_phone_number_id}/messages",
        headers=_headers(),
        json={"messaging_product": "whatsapp", "to": to,
              "type": "text", "text": {"body": body[:4096]}},
        timeout=15,
    )
    if r.status_code >= 400:
        log.error("send_text failed %s: %s", r.status_code, r.text)
    return r


def send_buttons(to: str, body: str, buttons: list[dict]):
    """buttons: [{id, title}] max 3, titles <= 20 chars."""
    if not buttons:
        return send_text(to, body)
    payload = {
        "messaging_product": "whatsapp", "to": to, "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body[:1024]},
            "action": {"buttons": [
                {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
                for b in buttons[:3]
            ]},
        },
    }
    r = httpx.post(f"{GRAPH}/{settings.wa_phone_number_id}/messages",
                   headers=_headers(), json=payload, timeout=15)
    if r.status_code >= 400:
        log.error("send_buttons failed %s: %s - falling back to text", r.status_code, r.text)
        return send_text(to, body)
    return r


def download_media(media_id: str, suffix: str = "") -> str:
    """Fetch media to a temp file, return its path. Caller deletes after
    hashing - media is never kept at rest (DPDP)."""
    meta = httpx.get(f"{GRAPH}/{media_id}", headers=_headers(), timeout=15).json()
    url = meta["url"]
    data = httpx.get(url, headers=_headers(), timeout=60).content
    f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="parakh_m_")
    f.write(data)
    f.close()
    return f.name
