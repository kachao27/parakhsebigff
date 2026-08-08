"""FR4 verdict engine. Strict layer order L1 -> L2 -> L3 -> L4.

Verdict policy (PRD §5):
- RED only from registry debarred match, rule conviction, or memory match.
  Citation mandatory; every red names its layer.
- GREEN only from registry verification; always carries the not-a-promise line.
- AMBER for everything else, with reasons and next steps. L4 alone never reds.
"""
import hashlib
import re
from dataclasses import dataclass, field

from ..rules import RULES
from ..router import Artifact
from . import l1_registry, l2_rules, l2_vision, l3_memory, l4_models, osint, campaign_intel


@dataclass
class Verdict:
    color: str                 # red | green | amber
    title: str
    layer: str | None          # L1_REGISTRY | L2_RULES | L3_MEMORY | None
    reasons: list[str] = field(default_factory=list)
    citation: str | None = None
    ref_id: str | None = None  # rule id / reg_no / fingerprint id
    lang: str = "en"
    artifact_hash: str = ""
    artifact_kind: str = ""
    advisory_ref: str | None = None
    signals: list[str] = field(default_factory=list)  # L4, amber-only
    # Set on an advice verdict when an identity is worth a (slow) OSINT web
    # check - the caller runs it out-of-band and sends a follow-up.
    pending_name: str = ""
    pending_handles: list = field(default_factory=list)
    advice_summary: str = ""


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()[:16]


def check_text(artifact: Artifact) -> Verdict:
    lang = artifact.lang
    h = _hash_text(artifact.value)
    base = dict(lang=lang, artifact_hash=h, artifact_kind=artifact.type)

    # ---------- L1 Registry ----------
    reg = None
    if artifact.type == "reg_no":
        reg = l1_registry.by_reg_no(artifact.value)
    elif artifact.type == "phone":
        reg = l1_registry.by_phone(artifact.value)
    elif artifact.type == "name_query":
        reg = l1_registry.by_name(artifact.value)

    if reg is not None and reg["status"] in ("debarred", "cautioned"):
        if reg["status"] == "debarred":
            title, reason = "DEBARRED ENTITY", f"{reg['name']} appears on SEBI/exchange debarment lists."
        else:
            title, reason = "NAMED IN ADVISORY", (
                f"{reg['name']} is named in a SEBI/exchange investor advisory as an "
                "unregistered or illegal operation.")
        return Verdict(
            "red", title, "L1_REGISTRY",
            reasons=[reason],
            citation=f"{reg['source'] or 'SEBI/exchange advisory'}",
            ref_id=reg["reg_no"] or reg["name"], **base,
        )

    # ---------- L2 Rules (pitch text, and text around identifiers) ----------
    if artifact.type in ("pitch_text",):
        hits = l2_rules.regex_convictions(artifact.value, artifact.embedded)
        mapper = "regex"
        if not hits:
            rid = l2_rules.llm_map(artifact.value)
            if rid:
                hits, mapper = [rid], "llm"
        if hits:
            shown = hits[:2]
            return Verdict(
                "red", "ILLEGAL OFFER", "L2_RULES",
                reasons=[RULES[r][lang if lang in ("en", "hi") else "en"] for r in shown],
                citation=" · ".join(RULES[r]["citation"] for r in shown),
                ref_id="+".join(shown), **base,
            )

    # ---------- L3 Memory (blacklist on the artifact itself + embedded) ----------
    checks = [(artifact.type, artifact.value)] if artifact.type in ("phone", "upi", "url") else []
    for kind in ("phone", "upi", "url"):
        checks += [(kind, v) for v in artifact.embedded.get(kind, [])]
    for kind, value in checks:
        bl = l3_memory.blacklist_lookup(kind, value)
        if bl is not None:
            return Verdict(
                "red", "MATCHED KNOWN FAKE", "L3_MEMORY",
                reasons=[f"This {kind.upper() if kind == 'upi' else kind} is on a confirmed scam blacklist."],
                citation=bl["ref"] or bl["source"] or "Parakh confirmed-fake registry",
                ref_id=f"{kind}:{value}", advisory_ref=bl["ref"], **base,
            )

    # ---------- GREEN: registry verification ----------
    if reg is not None and reg["status"] == "active":
        since = f" · since {reg['valid_till'][:4]}" if reg["valid_till"] else ""
        if artifact.type == "phone":
            note = (
                "This number is listed as the registered contact of this entity in SEBI's published list."
                if (reg["source"] or "").startswith("sebi:")
                else "This number is linked to a registered entity (seed data mapping)."
            )
        else:
            note = "Verified in the SEBI registry."
        return Verdict(
            "green", "SEBI REGISTERED", "L1_REGISTRY",
            reasons=[f"{reg['name']} · {reg['reg_no']}{since}", note,
                     "Registration is not a promise of returns."],
            citation=f"Registry record · {reg['source'] or 'SEBI'}",
            ref_id=reg["reg_no"], **base,
        )

    # ---------- AMBER ----------
    signals = []
    urls = ([artifact.value] if artifact.type == "url" else []) + artifact.embedded.get("url", [])
    for u in urls:
        signals += l4_models.url_signals(u)

    if artifact.type == "phone":
        reasons = ["No registered entity is publicly associated with this number.",
                   "That alone does not make it a scam - but do not act on advice from it."]
    elif artifact.type == "reg_no":
        reasons = ["This registration number was not found in the registry.",
                   "A genuine adviser's number will verify. Treat this claim with caution."]
    elif artifact.type == "upi":
        reasons = ["This UPI ID is not a verified @valid handle and is not on our blacklist.",
                   "Registered advisers collect fees through verified handles. Pause before paying."]
    elif artifact.type == "name_query":
        reasons = ["No registered entity matched this name closely enough to verify.",
                   "Ask for their SEBI registration number and check it here."]
    else:
        reasons = ["No rule violation or known-scam match was found.",
                   "Absence of a red flag is not a clean bill - verify who is asking before acting."]

    return Verdict("amber", "CAUTION - VERIFY FIRST", None,
                   reasons=reasons, signals=signals, **base)


def check_link(url: str, lang: str = "en") -> Verdict:
    """Identify and verify the creator behind a video/social LINK using real
    source metadata (uploader, channel, title, description) - never a guessed
    face. Then run the claim-check on the text and the registry/advisory check
    on the actual uploader.
    """
    from .. import linkmeta
    from ..router import classify_text
    h = _hash_text(url)
    base = dict(lang=lang, artifact_hash=h, artifact_kind="url")

    # blacklisted link is an instant red regardless of metadata
    bl = l3_memory.blacklist_lookup("url", url)
    if bl is not None:
        return Verdict("red", "MATCHED KNOWN FAKE", "L3_MEMORY",
                       reasons=["This link is on a confirmed scam blacklist."],
                       citation=bl["ref"] or bl["source"] or "Parakh blacklist",
                       ref_id=f"url:{url}", advisory_ref=bl["ref"], **base)

    meta = linkmeta.fetch_metadata(url)
    if meta is None:
        v = check_text(classify_text(url))  # fall back to URL heuristics
        return v

    text = f"{meta['title']}\n{meta['description']}".strip()
    uploader = (meta.get("uploader") or meta.get("channel") or "").strip()

    # claim-check the real title/description
    if text:
        tv = check_text(classify_text(text))
        if tv.color == "red":
            tv.artifact_hash = h
            tv.artifact_kind = "url"
            return tv

    # verify the actual uploader against the registry
    if uploader:
        reg = l1_registry.by_name(uploader)
        if reg is not None and reg["status"] == "active":
            return Verdict("green", "REGISTERED ADVISER", "L1_REGISTRY",
                           reasons=[f"Source account “{uploader}” resolves to {reg['name']} · {reg['reg_no']}, "
                                    "SEBI-registered.",
                                    "Registration is not a promise of returns - judge the advice on its merits."],
                           citation=f"Registry record · {reg['source'] or 'SEBI'}", ref_id=reg["reg_no"], **base)
        if reg is not None and reg["status"] in ("debarred", "cautioned"):
            return Verdict("red", "NAMED IN ADVISORY" if reg["status"] == "cautioned" else "DEBARRED ENTITY",
                           "L1_REGISTRY",
                           reasons=[f"Source account “{uploader}” is {reg['status']} by SEBI/exchange."],
                           citation=reg["source"] or "SEBI/exchange advisory",
                           ref_id=reg["reg_no"] or reg["name"], **base)

    # no registry hit - hand the real uploader to the OSINT follow-up
    title = "SOURCE IDENTIFIED - VERIFYING"
    reasons = [f"Source: “{meta['title']}” by *{uploader or 'unknown uploader'}*.",
               "🔍 Checking this account against SEBI, NSE and BSE now."]
    if not uploader:
        reasons = [f"Source: “{meta['title']}”. The uploader is not clearly identified.",
                   "Treat unattributed stock advice with caution - verify any adviser in SEBI's registry."]
    v = Verdict("amber", title, None, reasons=reasons, **base)
    v.pending_name = uploader
    return v


def enrich_identity(name: str, handles: list | None = None) -> dict:
    """Slow OSINT web check for an advice verdict, run out-of-band. Returns a
    follow-up: {color, title, text} where color escalates to red iff the entity
    is flagged in a public advisory with a source (never on a search alone)."""
    result = osint.authenticity_check(name, handles or [])
    if result is None:
        return {"color": "amber", "title": "CHECK YOURSELF",
                "text": f"Could not complete the web check on “{name}”. "
                        "Verify them in SEBI's registry at sebi.gov.in before acting."}
    if result.get("flagged") and result.get("source"):
        return {"color": "red", "title": "🔴 NAMED IN ADVISORY",
                "text": f"“{name}” is flagged in a public advisory / fraud record:\n{result.get('summary','')}\n\n"
                        f"Source: {result['source']}\n\nDo not act on this advice or send anyone money."}
    if result.get("registered") is True:
        return {"color": "amber", "title": "🟢 POSSIBLY REGISTERED",
                "text": f"Web check suggests “{name}” may be SEBI-registered. Confirm the exact registration "
                        "number in SEBI's registry before acting - registration is not a promise of returns."}
    return {"color": "amber", "title": "🟡 COULDN'T CONFIRM - CHECK THE REGISTRY",
            "text": f"My web search did not surface a registration or an advisory for “{name}”. This does "
                    "NOT mean they are unregistered - many advisers are registered under a firm name. "
                    "Confirm directly at sebi.gov.in before acting, and never pay based on a video alone."}


def check_media(path: str, kind: str, ocr_text: str | None = None, lang: str = "en") -> Verdict:
    """kind: image | video | audio. Fingerprint match first; OCR text runs the text path."""
    if kind == "video":
        hashes = l3_memory.video_hashes(path)
    elif kind == "audio":
        hashes = l3_memory.audio_hashes(path)
    else:
        hashes = l3_memory.image_hashes(path)
    h = hashes[0] if hashes else ""
    base = dict(lang=lang, artifact_hash=h, artifact_kind=kind)

    hit = l3_memory.match_fingerprint(hashes, kind)
    if hit is not None:
        fp, dist = hit
        return Verdict(
            "red", "CONFIRMED FAKE", "L3_MEMORY",
            reasons=[fp["label"], f"Matches a confirmed fake on record (distance {dist}/64)."],
            citation=fp["advisory_ref"] or "Parakh fingerprint registry",
            ref_id=f"FP{fp['id']}", advisory_ref=fp["advisory_ref"], **base,
        )

    # Read the CONTENT, not just the caption. A deepfake's fraud lives in the
    # spoken pitch and on-screen text - extract both and run the claim-check.
    # This is the deck's thesis: the claim itself is the evidence, no prior
    # victim (and no fingerprint) needed.
    from ..transcribe import transcribe
    parts = [ocr_text or ""]
    if kind in ("video", "audio"):
        parts.append(transcribe(path))       # spoken pitch
    if kind == "video":
        from ..ocr import extract_text
        for frame in l3_memory.video_keyframes(path)[:6]:
            parts.append(extract_text(frame))  # on-screen text overlays
    content = "\n".join(p for p in parts if p and p.strip()).strip()

    # Fast deterministic pass on extracted content (regex rules).
    if content:
        from ..router import classify_text
        art = classify_text(content)
        text_verdict = check_text(art)
        if text_verdict.color == "red":
            text_verdict.artifact_hash = h or text_verdict.artifact_hash
            text_verdict.artifact_kind = kind
            text_verdict.lang = art.lang
            return text_verdict

    # Deep multimodal pass (the LLM half of L2): reads burned-in subtitles and
    # Hinglish natively; maps to a rule id or NONE only.
    signals = []
    advice_flag = False
    creator = ""
    advice_summary = ""
    if kind == "video":
        judge = l2_vision.judge_media(path, content)
        if judge is not None:
            if judge.get("rule_id"):
                rid = judge["rule_id"]
                rule = RULES[rid]
                return Verdict(
                    "red", "ILLEGAL OFFER", "L2_RULES",
                    reasons=[rule[lang if lang in ("en", "hi") else "en"]],
                    citation=rule["citation"], ref_id=rid, **base,
                )
            if judge.get("impersonation_detected") and judge.get("impersonated_entity"):
                who = judge["impersonated_entity"]
                signals.append(
                    f"this appears to present as {who} - market officials and regulators do not "
                    "give stock tips or run investment groups; treat as impersonation")
            advice_flag = judge.get("gives_stock_advice", False)
            creator = (judge.get("creator_name") or "").strip()
            speaker = (judge.get("speaker_name") or "").strip()
            handles = [h for h in (judge.get("handles") or []) if h]
            advice_summary = (judge.get("advice_summary") or "").strip()

            # Cross-check every identity artifact the video revealed. Any of
            # these can CONVICT deterministically - no guessing.
            claimed = (judge.get("claimed_reg_no") or "").strip().upper()
            if re.match(r"^IN[A-Z]\d{9}$", claimed):
                if l1_registry.by_reg_no(claimed) is None:
                    return Verdict(
                        "red", "ILLEGAL OFFER", "L2_RULES",
                        reasons=[RULES["R6"][lang if lang in ("en", "hi") else "en"],
                                 f"The number it claims ({claimed}) is not in SEBI's registry."],
                        citation=RULES["R6"]["citation"], ref_id="R6", **base,
                    )
            for c in (judge.get("contacts") or []):
                for kind in ("phone", "upi", "url"):
                    from ..router import RE_PHONE, RE_UPI, RE_URL
                    pat = {"phone": RE_PHONE, "upi": RE_UPI, "url": RE_URL}[kind]
                    for val in pat.findall(c):
                        v = val if isinstance(val, str) else val
                        bl = l3_memory.blacklist_lookup(kind, v)
                        if bl is not None:
                            return Verdict(
                                "red", "MATCHED KNOWN FAKE", "L3_MEMORY",
                                reasons=[f"This video shows a {kind} on a confirmed scam blacklist."],
                                citation=bl["ref"] or bl["source"] or "Parakh blacklist",
                                ref_id=f"{kind}:{v}", advisory_ref=bl["ref"], **base,
                            )

            # Name the person: prefer the actual speaker over a clip-channel brand.
            name_to_check = speaker or creator
            if advice_flag and name_to_check:
                reg = l1_registry.by_name(name_to_check)
                if reg is not None and reg["status"] == "active":
                    return Verdict(
                        "green", "REGISTERED ADVISER", "L1_REGISTRY",
                        reasons=[f"{reg['name']} · {reg['reg_no']} is SEBI-registered to give this advice.",
                                 "Registration is not a promise of returns - judge the advice on its merits."],
                        citation=f"Registry record · {reg['source'] or 'SEBI'}",
                        ref_id=reg["reg_no"], **base,
                    )
                if reg is not None and reg["status"] in ("debarred", "cautioned"):
                    return Verdict(
                        "red", "NAMED IN ADVISORY" if reg["status"] == "cautioned" else "DEBARRED ENTITY",
                        "L1_REGISTRY",
                        reasons=[f"{reg['name']} is giving stock advice but is {reg['status']} by SEBI/exchange."],
                        citation=reg["source"] or "SEBI/exchange advisory",
                        ref_id=reg["reg_no"] or reg["name"], **base,
                    )

    score = l4_models.media_signal(path, kind)
    if score is not None and score > 0.6:
        signals.append("this media shows signs of manipulation - treat with caution")

    kindword = {"video": "video", "audio": "voice note", "image": "image"}.get(kind, "media")
    if signals and any("impersonation" in s for s in signals):
        title = "LIKELY IMPERSONATION - DO NOT ACT"
        reasons = ["No confirmed-fake match yet, but the content reads as an impersonation of a market figure.",
                   "No official gives stock tips this way. Do not join any group or pay anyone."]
    elif advice_flag:
        # Only trust text that is literally on screen (a watermark/handle) -
        # NEVER a name the model inferred from a face. `creator` is such text;
        # `speaker` is used only if the judge saw/heard it explicitly, and even
        # then we frame it as unverified and ask for the link.
        onscreen = creator.strip()
        what = f" ({advice_summary})" if advice_summary else ""
        title = "UNVERIFIED ADVICE - SEND THE SOURCE LINK"
        reasons = [f"This video gives stock advice{what} to the public.",
                   "Only a SEBI-registered adviser or research analyst may do this. We do not guess who a "
                   "face belongs to - so we cannot confirm the person from the clip alone."]
        if onscreen:
            reasons.append(f"The clip is watermarked “{onscreen}”. "
                           "🔍 Checking that account against SEBI now.")
        reasons.append("For a definitive answer, reply with the original link (YouTube, Instagram, etc.) "
                       "and I will identify the real creator from the source and check their SEBI status.")
        v = Verdict("amber", title, None, reasons=reasons, signals=signals, **base)
        v.pending_name = onscreen        # verifiable on-screen handle only (may be "")
        v.pending_handles = handles
        v.advice_summary = advice_summary
        return v
    else:
        title = "NOT A KNOWN FAKE - STAY ALERT"
        reasons = [f"We read this {kindword} - its on-screen text and spoken words - and found "
                   "no illegal offer, and no match to a confirmed fake on record."]
        reasons.append("Absence of a red flag is not a clean bill. Verify who is behind it: "
                       "are they in SEBI's registry? Is any offer they make even legal?"
                       if content else
                       "We could not extract readable speech or text. Forward the offer as text "
                       "and I will check the claim itself.")
    return Verdict("amber", title, None, reasons=reasons, signals=signals, **base)
