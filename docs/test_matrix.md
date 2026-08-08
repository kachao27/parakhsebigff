# Format test matrix

Automated: `PATH=/opt/homebrew/bin:$PATH .venv/bin/python -m pytest tests/ -q` (28 tests).

| # | Format | Path tested | Expected | Automated |
|---|--------|-------------|----------|-----------|
| 1 | Pitch text (EN) | web + webhook | 🔴 ILLEGAL OFFER, rule ids + citation | ✅ |
| 2 | Pitch text (HI) | web + webhook | 🔴 Hindi card (गैरकानूनी ऑफर) | ✅ |
| 3 | Reg no (real, scraped) | web | 🟢 SEBI REGISTERED | ✅ |
| 4 | Reg no (unknown) | web | 🟡 not found | ✅ |
| 5 | Name (real, fuzzy) | web | 🟢 with reg number | ✅ |
| 6 | Name (unknown) | web | 🟡 | ✅ |
| 7 | Phone (mapped) | web + contact card | 🟢 registered contact | ✅ |
| 8 | Phone (unknown) | web | 🟡 exact PRD phrasing | ✅ |
| 9 | UPI (blacklisted) | web | 🔴 MATCHED KNOWN FAKE | ✅ |
| 10 | UPI (unknown) | web | 🟡 @valid guidance | ✅ |
| 11 | URL (lookalike) | web | 🟡 + L4 signals | ✅ |
| 12 | Debarred entity | web | 🔴 DEBARRED ENTITY | ✅ |
| 13 | Screenshot with scam text (OCR) | web + webhook | 🔴 via text path | ✅ |
| 14 | Clean image | web | 🟡 | ✅ |
| 15 | Fingerprinted video | web | 🔴 CONFIRMED FAKE | ✅ |
| 16 | Cropped + re-encoded copy | web + webhook | 🔴 CONFIRMED FAKE | ✅ |
| 17 | Clean video | web | 🟡 | ✅ |
| 18 | Fingerprinted voice note (re-encoded) | webhook | 🔴 CONFIRMED FAKE | ✅ |
| 19 | Contact card | webhook | routes to phone path | ✅ |
| 20 | Button replies (report/advisory/block) | webhook | confirmation texts | ✅ (report) |
| 21 | Sightings + campaign clustering | webhook ×3 | campaign forms at threshold | ✅ |
| 22 | Red cards carry citation + layer | all | invariant asserted | ✅ |
| 23 | 20 legit messages | rules layer | zero convictions | ✅ |

**Manual (real phone, before demo)** — transport itself, already proven live for text:
image / video / voice note / contact via actual WhatsApp; button taps; advisory
push arriving on both phones; Hindi input from a Hindi-locale keyboard.

Codec note: WhatsApp voice notes are Opus — verified matching at distance 10/64
(threshold boundary). If a real-device voice note misses, re-fingerprint from a
WhatsApp-downloaded copy of the same clip (same codec both sides → distance ~0).
