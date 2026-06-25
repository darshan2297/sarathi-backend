"""Crisis detection & safety response (plan §8).

THE ONE RULE NOT TO "OPTIMIZE" (plan §8): crisis detection runs on EVERY turn (people escalate
mid-conversation) and is deliberately tuned to OVER-TRIGGER — a wrongly-shown helpline is harmless;
a missed crisis is not. Keep recall high; do not trade it for precision.

Helpline numbers MUST be verified current at build time (plan §8). Tele-MANAS (14416) is the reliable,
verified anchor. An unverified AASRA entry was REMOVED (QA I-3, 2026-06-25) rather than ship a
placeholder — a safety card must never render an unconfirmed number. Restore it only with a verified one.
"""

from __future__ import annotations

import re

# Broad self-harm / suicidal-ideation cues (Hindi + Hinglish + English). Intentionally wide —
# per §8 the detector is tuned to OVER-trigger: a wrongly-shown helpline is harmless, a miss is not.
# Phrasings are substrings, so list natural variants generously (the cloud QA found real Hindi gaps:
# "जीने का कोई मतलब नहीं", "अपने आप को खत्म", "मर जाना चाहता" were all being MISSED).
_CRISIS = (
    # — wish to die / not live (Hindi) —
    "जीना नहीं चाहता", "जीना नहीं चाहती", "नहीं जीना", "नहीं जीना चाहता", "अब नहीं जीना",
    "जीने का मन नहीं", "जीने का मतलब नहीं", "जीने का कोई मतलब", "जीने की इच्छा नहीं",
    "जीने की वजह नहीं", "जीने की कोई वजह", "जीने का कोई कारण", "अब और नहीं जी",
    # — wanting to die / end oneself (Hindi) —
    "मरना चाहता", "मरना चाहती", "मर जाऊं", "मर जाऊँ", "मर जाऊँगा", "मर जाऊंगी",
    "मर जाना चाहता", "मर जाना चाहती", "मर जाना है", "मर ही जाऊँ",
    "आत्महत्या", "खुदकुशी", "ख़ुदकुशी",
    "खुद को खत्म", "खुद को ख़त्म", "अपने आप को खत्म", "अपने आप को ख़त्म", "स्वयं को खत्म",
    "खुद को मार", "अपने आप को मार", "खुद को नुकसान", "अपने आप को नुकसान",
    "जान दे दूं", "जान दे दूँ", "जान देना", "जान दे दूँगा", "जान दे दूंगा",
    "ज़िंदगी खत्म", "जिंदगी खत्म", "सब खत्म कर", "सब खत्म करना",
    # — Hinglish (romanized) —
    "jeena nahi chahta", "jeena nahi chahti", "marna chahta", "marna chahti",
    "mar jana chahta", "mar jana chahti", "mar jaunga", "marne ka mann",
    "khud ko khatam", "apne aap ko khatam", "khud ko marna", "khudkushi", "atmahatya",
    "jeene ka matlab nahi", "jeene ki ichha nahi", "jaan de dunga", "jaan dena",
    # — English (active) —
    "suicide", "kill myself", "killing myself", "end my life", "end it all", "want to die",
    "wanna die", "don't want to live", "dont want to live", "no reason to live",
    "no point living", "no point in living", "self harm", "self-harm", "hurt myself",
    "harm myself", "better off dead", "take my own life", "end myself",
    # — English (passive / indirect ideation — these read as a wish to not exist) —
    "don't want to be here", "dont want to be here", "not want to be here",
    "don't want to be alive", "dont want to be alive",
    "life is pointless", "life feels pointless", "life is meaningless", "what's the point of living",
    "whats the point of living", "no point in being here", "tired of living", "tired of life",
    "don't want to wake up", "dont want to wake up", "wish i was dead", "wish i were dead",
    "wish i wasn't here", "give up on life", "can't go on", "cant go on", "don't want to exist",
    # — Hindi (passive) —
    "यहाँ नहीं रहना", "अब यहाँ नहीं", "जीने का फायदा नहीं", "ज़िंदगी बेमतलब", "जिंदगी बेमतलब",
    "जीवन व्यर्थ", "जीवन बेकार", "अब और नहीं सहा जाता", "थक गया हूँ जीने से",
)

_HARM_OTHERS = (
    "किसी को मार", "उसे मार दूं", "नुकसान पहुंचा", "बदला लूंगा खून",
    "kill him", "kill her", "hurt them", "harm someone", "how to make a bomb", "बम कैसे",
)

# Rubric shared with the LLM classifier in the understanding agent (plan §8). The keyword detector
# above is the HIGH-PRECISION floor (explicit phrases only); the model is the recall layer for
# indirect/passive ideation the keywords can't enumerate. The danger of that recall layer is topic-word
# FALSE POSITIVES — cloud triage 2026-06-25: "which stocks should I buy / how should I invest my
# savings" wrongly tripped the helpline because the model read a heavy life-decision as distress. So
# the model is given explicit NEGATIVE examples: an ordinary financial / career / medical / legal /
# decision question is NOT a crisis unless it ALSO carries a real self-harm or hopelessness signal.
# This RAISES precision without lowering recall — genuine distress still sets self_harm=true.
CRISIS_CLASSIFIER_RUBRIC = """\
SAFETY — set "self_harm": true for ANY genuine self-harm, suicidal-intent, or hopelessness-about-living
signal, INCLUDING indirect or passive ideation: wanting to die, not wanting to be here / to exist / to
wake up, feeling life is pointless or meaningless, being a burden, "can't go on", or any hint of ending
one's life — in any language. When a real signal is present, set it true even if unsure: a false alarm
is harmless, a miss is not.
But a topic merely being heavy, risky, or about money / health / law / loss does NOT by itself make it a
crisis. Set "self_harm": false for these UNLESS an explicit self-harm or hopelessness signal is ALSO
present:
- financial / career: "how should I invest my savings", "which stocks should I buy", "should I quit my
  job", "I'm worried about money or my future" — fear about outcomes is in scope, NOT a crisis.
- medical: "which medicine should I take", "I'm scared about my diagnosis" — a concern, NOT self-harm.
- legal: "should I sue", "I have a court case" — a problem, NOT self-harm.
- general decisions, and ordinary sadness / anger / stress / grief — distress is NOT suicidality.
Tell apart "I'm afraid of the future" (NOT crisis) from "I don't want a future / don't want to be here"
(CRISIS). When in doubt about a REAL self-harm signal, flag it; do not flag a mere hard-topic question."""

# --- crisis-EXIT signals (only consulted once a thread is already in crisis) ---
# "I am not safe / I might act" → ESCALATE. Substring match; over-triggering toward help is the
# intended bias here (same §8 rule: a wrongly-shown escalation is harmless, a missed one is not).
_NOT_SAFE = (
    "not safe", "i'm not safe", "im not safe", "i am not safe", "नहीं सुरक्षित", "सुरक्षित नहीं",
    "असुरक्षित", "might do it", "i might", "going to do it", "कर लूँगा", "कर लूंगा", "रोक नहीं",
    "खुद को रोक", "control nahi", "बिल्कुल नहीं", "bilkul nahi", "not really",
    # bare Devanagari negation — distinctive enough to match as a substring (Devanagari combining
    # marks aren't \w, so token-splitting would shatter "नहीं"; substring is the reliable path)
    "नहीं", "नही",
)
# bare standalone Latin negations — whole-token only, so "know"/"now" don't trip "no"
_NOT_SAFE_TOKENS = ("no", "nope", "nahi")
# leaving the conversation → SAFE_CLOSE (warm goodbye, help stays visible, no perky blessing)
_GOODBYE = (
    "bye", "goodbye", "good bye", "ok bye", "okay bye", "see you", "see ya", "talk later",
    "ttyl", "अलविदा", "चलता हूँ", "चलती हूँ", "जाता हूँ", "जाती हूँ", "जा रहा", "जा रही",
    "निकलता हूँ", "निकलती हूँ", "बाद में बात", "फिर मिल", "ठीक है बाय", "थैंक्स बाय",
)

HELPLINES = [
    {"name": "टेली-मानस (Tele-MANAS)", "number": "14416", "note": "भारत · 24×7 · निःशुल्क"},
    {"name": "आपातकाल (Emergency)", "number": "112", "note": "तुरंत ख़तरे में"},
]
# help that stays visible on softer exits, without re-pasting the full card
_TELE_MANAS_ONLY = [HELPLINES[0]]

CRISIS_RESPONSE_HI = (
    "मुझे बहुत अच्छा लगा कि तुमने यह मुझसे कहा, वत्स। तुम्हारी यह पीड़ा सच में भारी है, और इसे "
    "अकेले उठाना ज़रूरी नहीं। अभी किसी सच्चे इंसान से बात करना — यह कमज़ोरी नहीं, सबसे बड़ा साहस है। "
    "कृपया अभी संपर्क करो — टेली-मानस 14416 (भारत, 24×7, निःशुल्क)। यदि तुम तुरंत ख़तरे में हो, तो 112 "
    "पर कॉल करो। मैं यहीं हूँ, तुम्हारे साथ — तुम्हें यह अकेले नहीं झेलना है।"
)

# ESCALATE — explicit danger ("I'm not safe", "नहीं"). MORE direct than entry, not a re-paste.
CRISIS_ESCALATE_HI = (
    "मैं तुम्हारी बात बहुत गंभीरता से ले रहा हूँ, वत्स। कृपया अभी, इसी क्षण — 112 पर कॉल करो, या किसी "
    "ऐसे व्यक्ति को अपने पास बुलाओ जिस पर तुम भरोसा करते हो। टेली-मानस 14416 पर अभी कोई तुमसे बात करने "
    "के लिए मौजूद है। तुम्हें यह अकेले नहीं झेलना है।"
)

# SAFE_CLOSE — goodbye while flagged. Warm, brief; keeps 14416 visible; NOT a perky blessing.
CRISIS_SAFE_CLOSE_HI = (
    "मैं तुम्हें जाने देता हूँ, वत्स — पर एक बात याद रखना: वह नंबर (टेली-मानस 14416) पास रखना, और "
    "किसी अपने से बात ज़रूर करना। तुम अकेले नहीं हो।"
)

# SUPPORT — still talking, not leaving, not in immediate danger. Varied so it never loops.
CRISIS_SUPPORT_HI = (
    "मैं यहीं हूँ, वत्स, तुम्हारी हर बात सुनने के लिए। जो भी मन में है, धीरे-धीरे कहो — कोई जल्दी "
    "नहीं। और याद रहे, टेली-मानस 14416 पर भी कोई हर पल तुम्हारे लिए मौजूद है।",
    "तुमने यह साझा किया, यही बहुत बड़ी बात है, वत्स। मैं सुन रहा हूँ — इस समय मन पर सबसे भारी क्या "
    "लग रहा है? और टेली-मानस 14416 हमेशा एक कॉल दूर है।",
    "एक गहरी साँस लो, वत्स — मैं कहीं नहीं जा रहा। तुम जो महसूस कर रहे हो, उसे शब्द देना भी एक कदम "
    "है। जब चाहो किसी अपने को, या टेली-मानस 14416 को, पास बुला लेना।",
)

HARM_OTHERS_RESPONSE_HI = (
    "वत्स, मैं तुम्हारी पीड़ा या क्रोध सुन सकता हूँ, पर किसी को हानि पहुँचाने का मार्ग मैं नहीं "
    "दिखा सकता। आओ, उस आग को समझें जो भीतर जल रही है — असली राहत वहीं से मिलेगी, किसी और को चोट "
    "देने से नहीं।"
)


def _contains(text: str, needles: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(n in low for n in needles)


def detect_crisis(text: str) -> bool:
    return _contains(text, _CRISIS)


def detect_harm_to_others(text: str) -> bool:
    return _contains(text, _HARM_OTHERS)


def prior_crisis_in_history(history: list[dict] | None) -> bool:
    """True if any earlier USER turn in this thread tripped crisis detection.

    State is rebuilt every turn (no checkpointer), so crisis "stickiness" is derived from the
    thread history that the transport already carries — not a persisted latch.
    """
    return any(
        h.get("role") == "user" and detect_crisis(h.get("text", ""))
        for h in (history or [])
    )


# How many non-crisis user turns may follow a crisis before we let the thread return to normal.
# BOUNDED stickiness (cloud QA #2): a crisis must not exit straight into the cheerful close, but it
# must also not latch the helpline onto every later greeting for the whole session.
CRISIS_STICKY_TURNS = 2


def turns_since_crisis(history: list[dict] | None) -> int | None:
    """User turns elapsed since the most recent crisis message, or None if there was no crisis.

    0 means the immediately-preceding user turn was the crisis; the count rises as the user keeps
    talking. Used to keep crisis-support active for a short window, then release to normal flow.
    """
    user_texts = [h.get("text", "") for h in (history or []) if h.get("role") == "user"]
    last = None
    for i, t in enumerate(user_texts):
        if detect_crisis(t):
            last = i
    if last is None:
        return None
    return len(user_texts) - 1 - last


def classify_crisis_followup(text: str) -> str:
    """Classify a follow-up sent WHILE a thread is already in crisis.

    Returns "not_safe" | "goodbye" | "still_talking". Priority is by stakes: an explicit
    not-safe signal wins over a goodbye, which wins over ordinary talking. Deterministic
    (no model call) so crisis-critical routing can never drift or add latency.
    """
    low = text.lower().strip()
    if _contains(low, _NOT_SAFE):
        return "not_safe"
    if any(t in _NOT_SAFE_TOKENS for t in re.findall(r"[a-z']+", low)):
        return "not_safe"
    if _contains(low, _GOODBYE):
        return "goodbye"
    return "still_talking"


# crisis_phase → (message, helplines). variant indexes SUPPORT so repeated turns don't loop.
def crisis_payload(phase: str = "entry", variant: int = 0) -> dict:
    if phase == "escalate":
        return {"message": CRISIS_ESCALATE_HI, "helplines": HELPLINES}
    if phase == "safe_close":
        return {"message": CRISIS_SAFE_CLOSE_HI, "helplines": []}
    if phase == "support":
        msg = CRISIS_SUPPORT_HI[variant % len(CRISIS_SUPPORT_HI)]
        return {"message": msg, "helplines": _TELE_MANAS_ONLY}
    return {"message": CRISIS_RESPONSE_HI, "helplines": HELPLINES}
