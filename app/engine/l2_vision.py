"""Multimodal claim judge for media (the LLM half of L2, PRD §4).

Sends video keyframes + the audio transcript to Claude, which reads burned-in
subtitles and Hinglish speech natively (no OCR/ASR quality loss) and makes the
nuanced call regex cannot. Constrained by structured output to a rule id or
NONE - it can never emit a free-text verdict, so a red still rests on a defined
SEBI rule with its citation, never on the model's opinion (deck promise P2).

Tuned for PRECISION: generic market commentary, education, and opinion return
NONE, so a legitimate finfluencer or registered adviser is never branded by the
algorithm (deck slide 7). Impersonation is returned as a signal, never a
conviction - the model can be wrong about who a face is.
"""
import base64
import json
import logging
import subprocess
import tempfile
from pathlib import Path

from ..config import settings
from ..rules import RULES

log = logging.getLogger("parakh.l2vision")

RULE_ENUM = list(RULES.keys()) + ["NONE"]

SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "rule_id": {"type": "string", "enum": RULE_ENUM},
            "impersonation_detected": {"type": "boolean"},
            "impersonated_entity": {"type": "string"},
            "gives_stock_advice": {"type": "boolean"},
            "creator_name": {"type": "string"},
            "speaker_name": {"type": "string"},
            "handles": {"type": "array", "items": {"type": "string"}},
            "contacts": {"type": "array", "items": {"type": "string"}},
            "claimed_reg_no": {"type": "string"},
            "advice_summary": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["rule_id", "impersonation_detected", "impersonated_entity",
                     "gives_stock_advice", "creator_name", "speaker_name", "handles",
                     "contacts", "claimed_reg_no", "advice_summary", "reason"],
        "additionalProperties": False,
    },
}

SYSTEM = (
    "You are the claim-checking layer of a SEBI investor-protection tool. You judge whether a "
    "forwarded finance video is a securities-fraud pitch, reading the on-screen (burned-in) text "
    "and the spoken words in any language including Hindi/Hinglish.\n\n"
    "Map to exactly ONE SEBI rule id if the content CLEARLY and explicitly matches it, else NONE:\n"
    "R1 guaranteed/assured/fixed returns or 'no loss'. R2 asks to hand over account login or offers to "
    "trade on the viewer's behalf. R3 advance fee to unlock/withdraw profits. R4 a paid tips/calls group "
    "or channel sold with profit claims. R5 fees to a personal UPI while claiming SEBI registration. "
    "R6 claims SEBI registration with no/invalid registration number. R7 pooling public money for trading. "
    "R8 offers institutional/FII account access. R9 guarantees IPO allotment for a fee. R10 asks to deposit "
    "more before withdrawal is allowed.\n\n"
    "PRECISION IS CRITICAL. General market commentary, investing philosophy, education, opinions, news, and "
    "a person merely describing their own strategy are NOT violations - return NONE. Only convict on an "
    "explicit illegal offer as defined above. When unsure, return NONE.\n\n"
    "Separately: set impersonation_detected true ONLY if the person claims to be, or is presented as, a "
    "specific named market official, exchange CEO, regulator, or well-known figure (deepfake risk) - not for "
    "an ordinary creator.\n\n"
    "gives_stock_advice: true if the video gives investment guidance of ANY kind to the public - stock "
    "recommendations, tips, 'which stocks to buy', how to allocate a specific amount, trading strategies "
    "pitched as a way to make returns, or portfolio guidance. In India only a SEBI-registered adviser/research "
    "analyst may do this, so this flag drives a registry check. It is FALSE only for genuine neutral education "
    "about concepts (e.g. 'what is a mutual fund'), pure news reporting, or a company's own results - content "
    "that recommends no action.\n\n"
    "Extract ONLY identity signals that are LITERALLY VISIBLE AS TEXT on screen or EXPLICITLY SPOKEN. "
    "This is critical: you must NEVER guess, infer, or recognise a person's name from their face, voice, or "
    "appearance. If a name is not written on screen and not spoken aloud, the field MUST be empty. Inventing a "
    "name would falsely accuse a real person - leave it blank instead.\n"
    "- creator_name: a channel/brand name or handle shown as an on-screen watermark/caption (e.g. 'BM Shorts', "
    "'@xyz'), else \"\". This is on-screen TEXT only, never who you think the face is.\n"
    "- speaker_name: the person's own name ONLY if it is written on screen or they say it ('main <name> hoon'). "
    "If you are inferring from the face/voice, leave it \"\". When in any doubt, \"\".\n"
    "- handles: social handles/usernames shown on screen or spoken, as an array (empty if none).\n"
    "- contacts: phone numbers, UPI IDs, or links shown on screen or spoken, as an array (empty if none).\n"
    "- claimed_reg_no: a SEBI registration number the video shows/claims (INH/INA/INZ + 9 digits), else \"\".\n"
    "advice_summary: one plain-English clause naming the guidance given (e.g. 'how to pick stocks with 5 lakh'), "
    "or \"\" if none. reason: one short internal sentence. Use \"\" or [] when a field is absent."
)


def _looks_clean(text: str) -> bool:
    """Heuristic: a usable transcript is mostly letters/spaces and not littered
    with the digit-salad and stray scripts a small ASR model emits on hard audio."""
    if not text or len(text) < 20:
        return False
    letters = sum(c.isalpha() or c.isspace() for c in text)
    digits = sum(c.isdigit() for c in text)
    return letters / len(text) > 0.75 and digits / len(text) < 0.12


def _duration(video_path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", video_path],
            capture_output=True, text=True, timeout=20)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _keyframes(video_path: str, n: int = 8) -> list[bytes]:
    """N frames spread EVENLY across the whole clip - burned-in subtitles change
    through the video, so sampling only the opening seconds misses the pitch."""
    out = tempfile.mkdtemp(prefix="parakh_vj_")
    dur = _duration(video_path)
    if dur > 1:
        fps = n / dur  # one frame every dur/n seconds -> ~n frames total
        vf = f"fps={fps:.4f},scale=512:-1"
    else:
        vf = "fps=1,scale=512:-1"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", video_path,
         "-vf", vf, "-frames:v", str(n), f"{out}/f%02d.jpg"],
        check=True, timeout=60,
    )
    return [p.read_bytes() for p in sorted(Path(out).glob("*.jpg"))[:n]]


def judge_media(video_path: str, transcript: str = "") -> dict | None:
    """Return the judge dict, or None if the LLM is unavailable/failed."""
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic

        frames = _keyframes(video_path)
        content = []
        for fb in frames:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg",
                           "data": base64.standard_b64encode(fb).decode()},
            })
        # The burned-in subtitles in the frames are ground truth. A rough
        # auto-transcript (esp. Hindi via a small model) is often noise and
        # hurts more than it helps, so only pass it when it looks clean.
        clean_transcript = transcript if _looks_clean(transcript) else ""
        text = ("These frames are sampled across the whole video. Read the burned-in on-screen "
                "text (captions/subtitles, any language including Hinglish) and the scene, and judge.")
        if clean_transcript:
            text += f"\n\nAuto-transcript (secondary; trust the on-screen text over this):\n{clean_transcript[:1500]}"
        content.append({"type": "text", "text": text})
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=settings.llm_model,
            max_tokens=400,
            system=SYSTEM,
            output_config={"format": SCHEMA},
            messages=[{"role": "user", "content": content}],
        )
        block = next(b.text for b in resp.content if b.type == "text")
        result = json.loads(block)
        result["rule_id"] = None if result["rule_id"] == "NONE" else result["rule_id"]
        return result
    except Exception as e:
        log.warning("vision judge unavailable: %s", e)
        return None
