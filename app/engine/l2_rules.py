"""L2 Rules: regex triggers plus an LLM paraphrase mapper that may only
output a rule id or none - never a free-text verdict. Structured output with
a strict enum schema enforces that at the API layer.
"""
import logging

from ..config import settings
from ..rules import RULES, REGISTRATION_CLAIM, REG_NO_FORMAT

log = logging.getLogger("parakh.l2")

RULE_ENUM = list(RULES.keys()) + ["NONE"]

MAPPER_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {"rule_id": {"type": "string", "enum": RULE_ENUM}},
        "required": ["rule_id"],
        "additionalProperties": False,
    },
}

MAPPER_SYSTEM = (
    "You map an investment-related message to exactly one SEBI rule violation id, or NONE.\n"
    "Rules:\n"
    "R1 guaranteed/assured returns promised. R2 asks for account login or offers to trade on the user's behalf. "
    "R3 advance fee demanded to unlock/withdraw profits. R4 joining fee for a tips group with profit claims. "
    "R5 fees to a personal UPI while claiming SEBI registration. R6 claims SEBI registration without a valid reg number. "
    "R7 pooling public money for trading. R8 offers institutional/FII account access. "
    "R9 guarantees IPO allotment for a fee. R10 asks to deposit more before withdrawal is allowed.\n"
    "Output NONE unless the message clearly matches a rule. Normal market talk, news, and genuine adviser "
    "communication are NONE. When uncertain, output NONE."
)


def regex_convictions(text: str, artifacts: dict) -> list[str]:
    hits = []
    for rid, rule in RULES.items():
        if rule["pattern"] and rule["pattern"].search(text):
            hits.append(rid)
    # Composite rules
    claims_reg = bool(REGISTRATION_CLAIM.search(text))
    if claims_reg and artifacts.get("upi"):
        hits.append("R5")
    if claims_reg and not REG_NO_FORMAT.search(text):
        hits.append("R6")
    return hits


def llm_map(text: str) -> str | None:
    """Return a rule id, or None. Only called when regex found nothing."""
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=256,
            system=MAPPER_SYSTEM,
            output_config={"format": MAPPER_SCHEMA},
            messages=[{"role": "user", "content": text[:2000]}],
        )
        import json

        block = next(b.text for b in response.content if b.type == "text")
        rid = json.loads(block)["rule_id"]
        return None if rid == "NONE" else rid
    except Exception as e:  # LLM is assistive, never load-bearing
        log.warning("llm_map failed: %s", e)
        return None
