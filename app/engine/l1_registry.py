"""L1 Registry: exact reg-no match, fuzzy name match (SequenceMatcher ratio
>= 0.85, documented threshold), phone lookup (seeded mapping - real registries
do not index phones, and the verdict copy never claims otherwise).
"""
import re
from difflib import SequenceMatcher

from ..db import get_db

NAME_MATCH_THRESHOLD = 0.85

# Generic words that carry no identity - dropped before token matching so a
# YouTube channel name ("Basant Maheshwari - The Equity Desk") still matches the
# registered firm ("Basant Maheshwari Wealth Advisers LLP").
_STOP = {
    "the", "equity", "desk", "shorts", "official", "channel", "show", "with",
    "wealth", "advisers", "adviser", "advisory", "advisors", "llp", "pvt",
    "private", "limited", "ltd", "research", "analyst", "analysts", "and",
    "associates", "capital", "market", "markets", "investment", "investments",
    "co", "company", "securities", "stock", "stocks", "trading", "academy",
    "finance", "financial", "services", "solutions", "group", "india",
}


def _tokens(name: str) -> set:
    return {t for t in re.findall(r"[a-z]+", (name or "").lower())
            if len(t) > 2 and t not in _STOP}


def by_reg_no(reg_no: str):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM registries WHERE reg_no = ?", (reg_no.upper(),)
        ).fetchone()


def by_phone(phone: str):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM registries WHERE phone = ?", (phone[-10:],)
        ).fetchone()


def by_name(name: str):
    """Best fuzzy match at or above threshold, else None."""
    q = name.strip().lower()
    qt = _tokens(name)
    best, best_score = None, 0.0
    with get_db() as db:
        rows = db.execute("SELECT * FROM registries").fetchall()
    for r in rows:
        rname = r["name"].lower()
        score = SequenceMatcher(None, q, rname).ratio()
        rt = _tokens(r["name"])
        # Strong token match: every distinctive query token (>=2, e.g. first +
        # last name) appears in the registry name. Catches channel-name -> firm.
        if len(qt) >= 2 and qt and qt <= rt:
            score = max(score, 0.95)
        # substantial substring also counts (suffixes like "Private Limited")
        elif len(q) >= 6 and (q in rname or rname in q):
            score = max(score, 0.9)
        if score > best_score:
            best, best_score = r, score
    if best_score >= NAME_MATCH_THRESHOLD:
        return best
    return None
