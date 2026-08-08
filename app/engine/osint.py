"""Identity authenticity check via web search - what a human investigator does.

Given a name/handle a video reveals about itself, search whether that entity is
(a) named in an official SEBI/NSE/BSE investor advisory, caution list, or
enforcement order, or credible fraud reporting, or (b) a publicly known
SEBI-registered adviser/analyst.

Precision-first and honest: if no such source is found, it returns "not found"
- absence of an advisory is NOT proof of wrongdoing, and the card says so. This
is a signal layer (L4-style): it can raise caution or corroborate, but a red
verdict still rests on a rule, a registry match, or a fingerprint - never on a
search result alone.
"""
import json
import logging
import re

from ..config import settings

log = logging.getLogger("parakh.osint")

SYSTEM = (
    "You verify an Indian stock-market content creator/entity against the securities regulators. Run SEVERAL "
    "web searches before concluding - try the name with each of: 'SEBI order', 'SEBI ban', 'NSE advisory', "
    "'BSE caution', 'dabba trading', 'unregistered investment adviser', 'fraud', and 'SEBI registered "
    "research analyst'. Search handles too if given.\n\n"
    "Decide: (1) flagged = is the entity named in an official SEBI/NSE/BSE investor advisory, caution list, "
    "debarment, or enforcement order, or in credible news of securities/investment fraud? (2) registered = "
    "is it a genuine SEBI-registered investment adviser or research analyst?\n\n"
    "Be precise: report flagged true ONLY with a concrete official/credible source URL; never fabricate one. "
    "Absence of a source is 'not found', not innocence, and not guilt. Prefer sebi.gov.in, nseindia.com, "
    "bseindia.com, and established news outlets.\n\n"
    "After searching, end your reply with ONE line of compact JSON and nothing after it:\n"
    '{"flagged": true|false, "registered": true|false|null, "summary": "<=25 words", "source": "<url or empty>"}'
)


def _extract_json(text: str) -> dict | None:
    for m in reversed(re.findall(r"\{[^{}]*\}", text)):
        try:
            d = json.loads(m)
            if "flagged" in d:
                return d
        except Exception:
            continue
    return None


def authenticity_check(name: str, handles: list[str] | None = None) -> dict | None:
    """Return {flagged, registered, summary, source} or None if unavailable."""
    if not settings.anthropic_api_key or not name:
        return None
    who = name + (f" (handles: {', '.join(handles)})" if handles else "")
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=settings.llm_model,
            max_tokens=1200,
            system=SYSTEM,
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}],
            messages=[{"role": "user", "content":
                       f'Entity to verify: "{who}". Search thoroughly across SEBI/NSE/BSE advisories, '
                       "enforcement orders, dabba-trading cautions, unregistered-adviser cases, fraud news, "
                       "and the SEBI registered-RA/RIA lists. Then give the JSON verdict."}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        result = _extract_json(text)
        if result:
            log.info("osint %s -> %s", name, result)
        return result
    except Exception as e:
        log.warning("osint unavailable: %s", e)
        return None
