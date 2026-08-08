"""FR5 verdict cards. One renderer for WhatsApp (text + up to 3 buttons)
and the web checker (same content, JSON). Hindi template when inbound was Hindi.
"""
from .engine.verdict import Verdict

EMOJI = {"red": "🔴", "green": "🟢", "amber": "🟡"}

LAYER_TAG = {
    "L1_REGISTRY": {"en": "Checked against: SEBI registry", "hi": "जांचा गया: SEBI रजिस्ट्री"},
    "L2_RULES": {"en": "Checked against: SEBI's rules", "hi": "जांचा गया: SEBI के नियम"},
    "L3_MEMORY": {"en": "Checked against: confirmed-fake registry", "hi": "जांचा गया: पुष्ट-नकली रजिस्ट्री"},
    None: {"en": "Checked: registry · rules · memory · models", "hi": "जांचा गया: रजिस्ट्री · नियम · मेमोरी · मॉडल"},
}

TITLES_HI = {
    "ILLEGAL OFFER": "गैरकानूनी ऑफर",
    "DEBARRED ENTITY": "प्रतिबंधित इकाई",
    "NAMED IN ADVISORY": "एडवाइजरी में नामित",
    "CONFIRMED FAKE": "पुष्ट नकली",
    "MATCHED KNOWN FAKE": "ज्ञात नकली से मेल",
    "SEBI REGISTERED": "SEBI रजिस्टर्ड",
    "CAUTION - VERIFY FIRST": "सावधान - पहले जांचें",
    "NOT A KNOWN FAKE - STAY ALERT": "ज्ञात नकली नहीं - सतर्क रहें",
    "LIKELY IMPERSONATION - DO NOT ACT": "संभावित प्रतिरूपण - कार्रवाई न करें",
    "UNVERIFIED ADVICE - CHECK WHO IS SPEAKING": "असत्यापित सलाह - जांचें कौन बोल रहा है",
    "REGISTERED ADVISER": "रजिस्टर्ड सलाहकार",
}

BUTTONS = {
    "report": {"en": "Report to SEBI", "hi": "SEBI को रिपोर्ट करें"},
    "advisory": {"en": "See advisory", "hi": "एडवाइजरी देखें"},
    "block": {"en": "Block sender", "hi": "भेजने वाले को ब्लॉक करें"},
}


def render_text(v: Verdict) -> str:
    lang = v.lang if v.lang in ("en", "hi") else "en"
    title = TITLES_HI.get(v.title, v.title) if lang == "hi" else v.title
    lines = [f"{EMOJI[v.color]} *{title}*", ""]
    lines += [f"• {r}" for r in v.reasons]
    for s in v.signals:
        lines.append(f"⚠️ Signal: {s}" if lang == "en" else f"⚠️ संकेत: {s}")
    if v.citation:
        lines += ["", f"_{v.citation}_"]
    lines += ["", f"_{LAYER_TAG[v.layer][lang]}_"]
    return "\n".join(lines)


def buttons_for(v: Verdict) -> list[dict]:
    lang = v.lang if v.lang in ("en", "hi") else "en"
    ids = []
    if v.color == "red":
        ids = ["report", "advisory", "block"] if v.advisory_ref else ["report", "block"]
    elif v.color == "amber":
        ids = ["report"]
    return [{"id": i, "title": BUTTONS[i][lang]} for i in ids]


def to_json(v: Verdict) -> dict:
    return {
        "color": v.color,
        "title": v.title,
        "layer": v.layer,
        "reasons": v.reasons,
        "signals": v.signals,
        "citation": v.citation,
        "ref_id": v.ref_id,
        "lang": v.lang,
        "artifact_hash": v.artifact_hash,
        "artifact_kind": v.artifact_kind,
        "buttons": [b["title"] for b in buttons_for(v)],
        "text": render_text(v),
    }
