"""FR3 artifact router: classify inbound into
{phone, upi, url, reg_no, pitch_text, image, video, audio, contact}
and extract embedded artifacts from longer text.
"""
import re
from dataclasses import dataclass, field

RE_REG_NO = re.compile(r"\bIN[A-Z]\d{9}\b")
RE_PHONE = re.compile(r"(?:\+?91[\s\-]?)?([6-9]\d{9})\b")
RE_URL = re.compile(
    r"\bhttps?://\S+|\bwww\.\S+|\b[\w\-]+\.(?:com|in|net|org|app|xyz|io|me|link|site|online|club)\b\S*",
    re.I,
)
# UPI: local@psp where psp has no dot (emails have TLD dots after @)
RE_UPI = re.compile(r"\b[\w.\-]{2,}@[a-zA-Z]{2,}\b(?!\.[a-zA-Z])")

DEVANAGARI = re.compile(r"[ऀ-ॿ]")


@dataclass
class Artifact:
    type: str            # phone | upi | url | reg_no | pitch_text | name_query | image | video | audio
    value: str
    lang: str = "en"
    embedded: dict = field(default_factory=dict)  # {phone: [...], upi: [...], url: [...], reg_no: [...]}


def detect_lang(text: str) -> str:
    return "hi" if DEVANAGARI.search(text or "") else "en"


def extract_embedded(text: str) -> dict:
    urls = [m.group(0) for m in RE_URL.finditer(text)]
    # strip URL spans before matching UPI/phone to avoid domain false positives
    stripped = RE_URL.sub(" ", text)
    return {
        "reg_no": RE_REG_NO.findall(text),
        "phone": RE_PHONE.findall(stripped),
        "upi": [u for u in RE_UPI.findall(stripped)],
        "url": urls,
    }


def classify_text(text: str) -> Artifact:
    """Route a text message. A short message that IS an identifier goes to the
    identity/payment path; anything longer is pitch_text with embedded artifacts."""
    t = text.strip()
    lang = detect_lang(t)

    m = RE_REG_NO.fullmatch(t.upper())
    if m:
        return Artifact("reg_no", t.upper(), lang)

    compact = re.sub(r"[\s\-]", "", t)
    if re.fullmatch(r"(\+?91)?[6-9]\d{9}", compact):
        return Artifact("phone", compact[-10:], lang)

    if RE_UPI.fullmatch(t) and "." not in t.split("@")[-1]:
        return Artifact("upi", t.lower(), lang)

    if RE_URL.fullmatch(t):
        return Artifact("url", t, lang)

    # short text with no scam-signal punctuation -> treat as a name lookup
    if len(t) < 60 and "\n" not in t and not extract_embedded(t)["upi"] and re.fullmatch(r"[A-Za-z .&()']+", t):
        return Artifact("name_query", t, lang, embedded=extract_embedded(t))

    return Artifact("pitch_text", t, lang, embedded=extract_embedded(t))
