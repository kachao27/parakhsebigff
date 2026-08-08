"""The claim on the deck: "a registered adviser is never branded by an
algorithm." This eval enforces it — 20 legitimate finance messages that must
produce ZERO red verdicts from the rules layer (regex path; the LLM mapper is
prompted to NONE on all of these and is never load-bearing).

Run: .venv/bin/python -m pytest tests/ -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.router import classify_text
from app.engine.l2_rules import regex_convictions

LEGIT = [
    "Your SIP of Rs 5,000 in HDFC Flexi Cap Fund was processed today.",
    "Markets closed higher today, Nifty up 1.2% led by banking stocks.",
    "Reminder: your mutual fund KYC needs updating before 31st August.",
    "Our research report on the cement sector is attached. Past performance is not indicative of future returns.",
    "Dear investor, your demat statement for July is available on the portal.",
    "The RBI kept the repo rate unchanged at 5.5% in today's policy.",
    "Quarterly results: revenue grew 14% year over year.",
    "Investments in securities are subject to market risk. Read all documents carefully.",
    "Your order to buy 10 shares of TCS has been executed at 4,102.",
    "Join our free webinar on how mutual fund taxation works.",
    "IPO of Sunrise Foods opens Monday. Price band 210-220. Please read the RHP.",
    "As a SEBI registered investment adviser (INA000098765), I charge a flat annual fee as per regulations.",
    "Gold ETFs saw record inflows last month, says AMFI data.",
    "Please complete your risk profiling questionnaire before our call.",
    "Dividend of Rs 12 per share has been credited to your bank account.",
    "The stock fell 8% after weak guidance; our analysts maintain a hold rating.",
    "Your account statement shows a realised gain of Rs 4,300 this quarter.",
    "We never ask for your OTP or password. Beware of fraudsters.",
    "Portfolio review call scheduled for Friday 4pm, please confirm.",
    "Long-term investing beats timing the market, says our latest newsletter.",
]


def test_no_false_red_on_legit_messages():
    failures = []
    for msg in LEGIT:
        art = classify_text(msg)
        if art.type != "pitch_text":
            continue  # identity path can't produce a rule conviction at all
        hits = regex_convictions(msg, art.embedded)
        if hits:
            failures.append((msg[:60], hits))
    assert not failures, f"legit messages wrongly convicted: {failures}"


def test_known_scams_still_convict():
    scams = [
        ('"Join VIP group. SEBI registered tips. 3% weekly guaranteed."', {"R1"}),
        ("Pay withdrawal tax of Rs 5000 to release your profit", {"R3"}),
        ("Guaranteed IPO allotment for a small fee, pakka confirmed", {"R9"}),
        ("Deposit 20% more to unlock withdrawal of your winnings", {"R10"}),
    ]
    for msg, expected in scams:
        art = classify_text(msg)
        hits = set(regex_convictions(msg, art.embedded))
        assert hits & expected, f"scam not caught: {msg} -> {hits}"
