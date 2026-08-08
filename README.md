# Parakh (परख)

**They can fake a face. They cannot fake a licence.**

A verdict machine for every investor, and a sensor network for the regulator, built on SEBI's own ground truth. Forward anything on WhatsApp (text, phone number, screenshot, video, UPI ID); get a verdict in seconds, in English or Hindi, with a citation instead of a probability.

*SEBI Securities Market TechSprint @ GFF 2026 · PS 1: AI-driven detection of synthetic media and phishing.*

## Live

- **Web checker:** http://64-227-171-1.sslip.io
- **Regulator dashboard:** http://64-227-171-1.sslip.io/dashboard
- **Demo video (3 min):** VIDEO_LINK_HERE

## Try it in 30 seconds

Paste these into the web checker, one at a time:

1. `Join VIP group. SEBI registered tips. 3% weekly guaranteed. Joining fee Rs 999.` returns RED, an illegal offer with the regulation cited. No prior victim needed; the claim itself is the evidence.
2. `Basant Maheshwari` returns GREEN, a SEBI-registered research analyst with the registration number, and the caution that registration is not a promise of returns.
3. `tradeinn.in` returns RED from memory, a URL on the confirmed-scam blacklist, with the exchange advisory attached.

Every card names the layer that produced the verdict.

## How a verdict is made

Four checks, strict order. **The law convicts; models assist.**

| Layer | Question | Nature |
|---|---|---|
| L1 Registry | Is this entity licensed? | deterministic |
| L2 Rules | Is this offer legal for *anyone* to make? | deterministic (regex + LLM paraphrase mapper constrained to a rule id or NONE; never a free-text verdict) |
| L3 Memory | Have we seen this exact fake? | network (pHash fingerprints, blacklists) |
| L4 Models | Does this look synthetic? | **signal only; can never produce red** |

**Verdict policy:** RED only from a debarred-registry match, a rule conviction, or a memory match, citation mandatory, layer named on every card. GREEN only from registry verification, always with "registration is not a promise of returns." Everything else is AMBER with reasons and next steps.

**Fakes die on first catch:** every keyframe of confirmed-fake media is hashed at three center crops; cropped, re-encoded, downscaled copies still match (Hamming ≤ 10/64, verified: 75% crop + re-encode matches at distance 0).

## Architecture

```
WhatsApp Cloud API ─┐                      ┌─ L1 registry (SQLite, seeded/scraped)
                    ├─ artifact router ────┤─ L2 rules catalog R1–R10
Web checker ────────┘   (phone/upi/url/    ├─ L3 fingerprint + blacklist memory
                         reg_no/pitch/     └─ L4 signals (URL heuristics, media model)
                         image/video)               │
                              │              verdict card (EN/HI, citation, layer tag)
                              ▼
                     sightings (hash only) ─▶ campaign radar ─▶ advisory push + evidence packet
```

## Honest scope (said plainly)

- Registry data is **seeded**, a few public rows plus realistic-format synthetic rows, all marked `seed:*` in the `source` column, until SEBI exposes a registry API (asking for that API is part of this pitch). `scripts/scrape_sebi.py` refreshes from public lists where the scrape succeeds.
- Phone→entity mappings are **seed data**: real registries do not index phone numbers, and the verdict copy never claims otherwise. An unknown number returns exactly: *"No registered entity is publicly associated with this number."*
- The deepfake model is a supporting signal **by design**, red verdicts come from memory and rules. Amber may cite a model signal but never asserts fake.
- English + Hindi ship now; the architecture is Bhashini-ready for 12+ languages.
- WhatsApp runs on the Cloud API test-number tier (5 recipients), sufficient for the prototype, stated openly.
- Ambiguous cases return amber with reasons and route to review, never a silent guess.

**DPDP:** no message content is ever stored. Sightings hold the artifact hash, type, verdict and rule/match id. Downloaded media is deleted immediately after hashing, nothing at rest. Sender wa_ids are retained solely to deliver advisory push-backs and can be purged.

## Run it locally (5 minutes)

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
brew install tesseract tesseract-lang ffmpeg     # OCR (eng+hin) + keyframes
cp .env.example .env                             # fill in tokens (all optional for web checker)
.venv/bin/python data/load_seeds.py
.venv/bin/uvicorn app.main:app --reload
```

- Web checker: http://localhost:8000
- Regulator dashboard: http://localhost:8000/dashboard
- Health: http://localhost:8000/health

Register a confirmed fake (before demoing the memory layer):

```bash
.venv/bin/python scripts/fingerprint_media.py path/to/clip.mp4 "Label for the card" "PA-001 advisory"
```

### WhatsApp (optional, web checker mirrors every flow)

1. developers.facebook.com → Create App (Business) → add WhatsApp → API Setup.
2. Copy the temporary token and phone_number_id into `.env`.
3. Expose the server (`railway up`, or a tunnel) and set the webhook to `{BASE_URL}/webhook` with your `WA_VERIFY_TOKEN`; subscribe to `messages`.
4. Add up to 5 recipient numbers on the test tier.

## Demo video seed

The demo clip is our own synthetic video of a **fictional** exchange official, clearly labelled. No real person is faked anywhere in this prototype.
