# Jury prep — the six hard questions

Thirty-second answers, each grounded in something the prototype actually does.

## 1. "Deepfake detectors get fooled. What happens when yours does?"

Nothing bad — because the detector can never convict. Red verdicts come only from
three deterministic sources: the registry (debarred), the rules (the claim itself is
illegal), and memory (an exact fingerprint match to a confirmed fake). The model is a
signal that can only make an amber more cautious. A scammer who beats the detector
still can't beat the law: "3% weekly guaranteed" is illegal *in text*, in any video,
from any face. We deliberately refuse the forgery arms race and fight on ground truth
that can't be faked. [Live: L4 code path is structurally unable to return red.]

## 2. "Registries don't index phone numbers. How do you verify a number?"

Correct, and the product never pretends otherwise. An unknown number returns exactly:
*"No registered entity is publicly associated with this number"* — not "this number is
not registered", because that claim is impossible today. Where we do map number → entity
it's marked seed data on the record itself. This gap is part of our ask: registered
intermediaries already declare contact details to SEBI at registration; exposing that
mapping via a registry API turns our amber into a real green — one schema change, no
new data collection.

## 3. "SEBI Check already exists. Why is this not redundant?"

SEBI Check verifies **payment handles** — it's pull-based, payment-only, and lives in a
separate portal you visit only after you already suspect. Parakh is the front door
*before* suspicion: it lives in the chat where the doubt happens, takes any artifact
(video, pitch, number, screenshot, UPI), and runs six defences at once — SEBI Check's
@valid logic is one of our four layers, not a competitor. And every query feeds the
regulator's campaign radar, which SEBI Check by design cannot do. We complete SEBI
Check; we don't duplicate it.

## 4. "DPDP — what do you store about users?"

No message content, ever. A sighting is: artifact hash, type, verdict, rule id,
timestamp, channel. Media is hashed and deleted in the same request — nothing at rest.
The one personal datum is the sender's WhatsApp id, kept solely to deliver advisory
push-backs, purgeable on request. Data minimisation isn't a compliance patch here;
the sensor network was designed to need only hashes. [Live: show the sightings table.]

## 5. "What if you falsely red-flag a registered adviser?"

Structurally hard by design. Green can only come from the registry; red can only come
from debarment, a per-se-illegal claim, or a confirmed-fake match — a model score can
never brand anyone. A registered adviser making legal claims gets green or amber, and
our regression suite includes 20 legitimate adviser/broker messages that must produce
zero convictions (including "SEBI registered adviser INA... charges a flat annual fee
per regulations"). If an adviser genuinely promises guaranteed returns, flagging that
is not a false positive — it's the law working. Ambiguity routes to amber and human
review, never silent conviction. [Live: tests/test_no_false_positives.py]

## 6. "Cold start — your fingerprint memory is empty on day one."

The memory layer is the *compounding* layer, not the load-bearing one. On day one,
rules and registry already convict the majority of retail scam patterns — no victim
needed, the claim itself is evidence. Memory then makes every catch permanent:
the first confirmation of a fake immunises everyone after, and exchange advisories
(BSE's deepfake advisories already name specific videos) can seed it before launch.
Singapore's ScamShield proves citizens will feed such a system at national scale —
120,000+ blocked entities started from zero too.
