"""AI campaign intelligence for the regulator console.

Given a clustered campaign (same artifact sighted repeatedly), Claude reads the
sighting pattern and the verdict basis and produces a structured brief the
regulator can act on: a plain-language summary, a threat level, the scam
mechanism, who is exposed, and a recommended action. Constrained by structured
output; cached on the campaign row so the dashboard stays instant.
"""
import json
import logging
import time

from ..config import settings

log = logging.getLogger("parakh.intel")

SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "threat_level": {"type": "string", "enum": ["critical", "high", "elevated"]},
            "headline": {"type": "string"},
            "summary": {"type": "string"},
            "mechanism": {"type": "string"},
            "who_is_exposed": {"type": "string"},
            "recommended_action": {"type": "string"},
        },
        "required": ["threat_level", "headline", "summary", "mechanism",
                     "who_is_exposed", "recommended_action"],
        "additionalProperties": False,
    },
}

SYSTEM = (
    "You are a securities-market surveillance analyst at SEBI. You write short, factual "
    "intelligence briefs on active scam campaigns detected by the Parakh sensor network. "
    "Base everything strictly on the data provided; do not invent facts or numbers. Be "
    "precise, calm and regulator-grade, not sensational.\n\n"
    "threat_level: critical (confirmed fake / debarred entity spreading fast), high "
    "(illegal offer convicted, multiple sightings), or elevated (repeated but lower-severity). "
    "headline: <=8 words naming the campaign. summary: 1-2 sentences on what is spreading and "
    "how fast. mechanism: the scam technique in one sentence (e.g. guaranteed-returns tips group, "
    "deepfake of an official, advance-fee). who_is_exposed: who receives it and the risk to them. "
    "recommended_action: the concrete regulator step (push advisory to affected users, refer to "
    "enforcement, coordinate takedown). Keep each field tight. Do not use dashes as punctuation."
)


def _basis_text(sample_verdict: str, ref_id: str) -> str:
    from ..rules import RULES
    parts = []
    v = (sample_verdict or "").split(":")[0]
    ref = (sample_verdict or "").split(":", 1)[-1] if ":" in (sample_verdict or "") else (ref_id or "")
    parts.append(f"verdict={v or 'red'}")
    for rid in (ref or "").replace("+", " ").split():
        if rid in RULES:
            parts.append(f"{rid}: {RULES[rid]['en']}")
    if not any(r in RULES for r in (ref or "").split("+")):
        parts.append(f"basis={ref}")
    return "; ".join(parts)


def generate(campaign: dict, timeline: list[dict]) -> dict | None:
    """campaign: a campaigns row (dict). timeline: [{ts, verdict, channel, kind}].
    Returns the intel dict or None if the LLM is unavailable."""
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic

        span_h = 0.0
        if timeline:
            span_h = (timeline[-1]["ts"] - timeline[0]["ts"]) / 3600.0
        velocity = f"{campaign['count']} sightings over {span_h:.1f} hours" if span_h > 0.05 \
            else f"{campaign['count']} sightings in minutes (fast burst)"
        channels = sorted({t.get("channel", "?") for t in timeline})

        facts = (
            f"Campaign PA-{campaign['id']:03d}\n"
            f"Artifact type: {campaign.get('kind') or 'text'}\n"
            f"Sightings: {campaign['count']}\n"
            f"Velocity: {velocity}\n"
            f"Channels: {', '.join(channels)}\n"
            f"Verdict basis: {_basis_text(campaign.get('sample_verdict',''), '')}\n"
            f"Status: {campaign.get('status')}\n"
        )
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=settings.llm_model,
            max_tokens=500,
            system=SYSTEM,
            output_config={"format": SCHEMA},
            messages=[{"role": "user", "content":
                       f"Write the brief for this campaign:\n\n{facts}"}],
        )
        block = next(b.text for b in resp.content if b.type == "text")
        intel = json.loads(block)
        intel["generated_at"] = time.time()
        return intel
    except Exception as e:
        log.warning("campaign intel failed: %s", e)
        return None
