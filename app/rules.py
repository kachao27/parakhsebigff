"""Rules catalog v1 (PRD §6). Each rule: regex trigger, one-line EN copy,
one-line HI copy, citation string.

Citation phrasing stays at the "SEBI's fraud regulations" level where
clause-precision is uncertain; legal pass scheduled before submission.
"""
import re

RULES = {
    "R1": {
        "pattern": re.compile(
            r"guarant\w+|assured\s+(returns?|profits?|income)|no[\s-]?loss"
            r"|fixed\s+\d+\s*%|\d+\s*%\s*(per\s+)?(week|weekly|month|monthly|daily|day)"
            r"|गारंट|निश्चित\s*(रिटर्न|मुनाफ|लाभ)|पक्का\s*(रिटर्न|मुनाफ)",
            re.I,
        ),
        "en": "Guaranteed or assured returns are illegal for anyone to offer, registered or not.",
        "hi": "गारंटीड या निश्चित रिटर्न का वादा करना किसी के लिए भी गैरकानूनी है, चाहे वह रजिस्टर्ड हो या नहीं।",
        "citation": "SEBI PFUTP Regulations, 2003 · IA/RA conduct regulations",
    },
    "R2": {
        "pattern": re.compile(
            r"(share|give|send|bhejo|de\s*do).{0,30}(login|password|credential|otp)"
            r"|we\s+(will\s+)?trade\s+(for|on behalf of)\s+you|account\s+handling"
            r"|अकाउंट\s*हैंडलिंग|आपके\s*लिए\s*ट्रेड",
            re.I,
        ),
        "en": "Handing over your account or credentials for someone else to trade is an unauthorised portfolio service.",
        "hi": "अपना अकाउंट या लॉगिन किसी और को ट्रेडिंग के लिए देना अनधिकृत पोर्टफोलियो सेवा है।",
        "citation": "Unauthorised portfolio management · SEBI RA/IA Regulations",
    },
    "R3": {
        "pattern": re.compile(
            r"(withdrawal|processing|release|unlock|activation|clearance)\s*"
            r"(tax|fee|charge|amount)|pay.{0,40}to\s+(withdraw|release|unlock)"
            r"|निकासी\s*(शुल्क|टैक्स|फीस)",
            re.I,
        ),
        "en": "A fee demanded to release or withdraw your own profits is a known fraud pattern.",
        "hi": "अपना ही मुनाफा निकालने के लिए फीस मांगना एक ज्ञात धोखाधड़ी पैटर्न है।",
        "citation": "SEBI PFUTP fraud pattern · I4C advisories",
    },
    "R4": {
        "pattern": re.compile(
            r"(joining|membership|entry|subscription)\s*(fee|charge|₹|rs)"
            r".{0,60}(tips?|calls?|group|channel|target)"
            r"|(vip|premium)\s+(tips?|calls?|group).{0,60}(profit|return|target|%)"
            r"|(profit|return|target|%).{0,60}(vip|premium)\s+(tips?|calls?|group)",
            re.I,
        ),
        "en": "Charging a fee for stock tips with profit claims is unregistered investment advice.",
        "hi": "मुनाफे के दावों के साथ स्टॉक टिप्स के लिए फीस लेना बिना रजिस्ट्रेशन निवेश सलाह है।",
        "citation": "SEBI Investment Advisers Regulations, 2013",
    },
    "R5": {
        "pattern": None,  # composite: registration claim + personal UPI (engine-evaluated)
        "en": "A registered adviser must not collect fees into a personal UPI ID; verified handles use @valid.",
        "hi": "रजिस्टर्ड सलाहकार व्यक्तिगत UPI में फीस नहीं ले सकते; सत्यापित हैंडल @valid उपयोग करते हैं।",
        "citation": "SEBI adviser fee-collection norms · @valid framework",
    },
    "R6": {
        "pattern": None,  # composite: "SEBI registered" claim with absent/invalid reg no (engine-evaluated)
        "en": "Claims to be SEBI registered, but no valid registration number is present. Verify against the registry.",
        "hi": "SEBI रजिस्टर्ड होने का दावा है, पर कोई मान्य रजिस्ट्रेशन नंबर नहीं है। रजिस्ट्री से जांचें।",
        "citation": "Impersonation of registered intermediary · verify at sebi.gov.in",
    },
    "R7": {
        "pattern": re.compile(
            r"pool(ing)?\s+(funds?|money|paisa)|invest\s+together|collective\s+(trading|fund)"
            r"|fund\s+collection|सामूहिक\s*निवेश|पैसा\s*जमा\s*कर",
            re.I,
        ),
        "en": "Pooling money from the public for trading is a collective investment scheme requiring registration.",
        "hi": "जनता से पैसा जमा कर ट्रेडिंग करना सामूहिक निवेश योजना है, जिसके लिए रजिस्ट्रेशन जरूरी है।",
        "citation": "SEBI CIS Regulations · unregistered fund activity",
    },
    "R8": {
        "pattern": re.compile(
            r"(fii|institutional|dii)\s+(account|access|quota|desk)|foreign\s+institutional\s+account",
            re.I,
        ),
        "en": "Offers of institutional or FII account access to retail investors are a known fraud pattern.",
        "hi": "आम निवेशकों को संस्थागत या FII अकाउंट एक्सेस देने का ऑफर एक ज्ञात धोखाधड़ी पैटर्न है।",
        "citation": "SEBI investor caution advisories",
    },
    "R9": {
        "pattern": re.compile(
            r"ipo.{0,40}(guaranteed?|confirmed|firm|pakka)\s*(allotment)?"
            r"|allotment.{0,30}guarant|गारंटीड\s*अलॉटमेंट",
            re.I,
        ),
        "en": "No one can guarantee IPO allotment for a fee. Allotment is by regulated process only.",
        "hi": "कोई भी फीस लेकर IPO अलॉटमेंट की गारंटी नहीं दे सकता। अलॉटमेंट केवल नियामित प्रक्रिया से होता है।",
        "citation": "Impersonation of RTA/exchange processes",
    },
    "R10": {
        "pattern": re.compile(
            r"(deposit|pay|add|invest)\s+[\w%₹.\s]{0,20}?(more|again|extra|further).{0,60}(withdraw|release|unlock)"
            r"|(withdraw|release).{0,50}(deposit|pay)\s+(more|first|again)"
            r"|और\s*(जमा|पैसे).{0,30}निकाल",
            re.I,
        ),
        "en": "Being asked to deposit more before you can withdraw is the classic pig-butchering unlock pattern.",
        "hi": "निकासी से पहले और पैसा जमा करने को कहना क्लासिक धोखाधड़ी पैटर्न है।",
        "citation": "SEBI PFUTP Regulations · I4C fraud pattern",
    },
}

REGISTRATION_CLAIM = re.compile(r"sebi\s*(registered|regd|certified)|सेबी\s*(रजिस्टर्ड|पंजीकृत)", re.I)
REG_NO_FORMAT = re.compile(r"\bIN[A-Z]\d{9}\b")
