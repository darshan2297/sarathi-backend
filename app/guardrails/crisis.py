"""Crisis detection & safety response (plan §8).

THE ONE RULE NOT TO "OPTIMIZE" (plan §8): crisis detection runs on EVERY turn (people escalate
mid-conversation) and is deliberately tuned to OVER-TRIGGER — a wrongly-shown helpline is harmless;
a missed crisis is not. Keep recall high; do not trade it for precision.

Helpline numbers MUST be verified current at build time (plan §8). Tele-MANAS is the reliable anchor;
the AASRA number is flagged for verification.
"""

from __future__ import annotations

# Broad self-harm / suicidal-ideation cues (Hindi + Hinglish + English). Intentionally wide.
_CRISIS = (
    "जीना नहीं चाहता", "नहीं जीना", "मरना चाहता", "मर जाऊं", "मर जाऊँ", "जान दे दूं",
    "जान देना", "आत्महत्या", "खुदकुशी", "खुद को खत्म", "खुद को ख़त्म", "जीने का मन नहीं",
    "ज़िंदगी खत्म", "जिंदगी खत्म", "सब खत्म कर", "खुद को नुकसान",
    "suicide", "kill myself", "end my life", "end it all", "want to die", "don't want to live",
    "dont want to live", "no reason to live", "self harm", "self-harm", "hurt myself",
)

_HARM_OTHERS = (
    "किसी को मार", "उसे मार दूं", "नुकसान पहुंचा", "बदला लूंगा खून",
    "kill him", "kill her", "hurt them", "harm someone", "how to make a bomb", "बम कैसे",
)

HELPLINES = [
    {"name": "टेली-मानस (Tele-MANAS)", "number": "14416", "note": "भारत · 24×7 · निःशुल्क"},
    {"name": "AASRA", "number": "+91-9820466726", "note": "verify-current-at-build"},
    {"name": "आपातकाल (Emergency)", "number": "112", "note": "तुरंत ख़तरे में"},
]

CRISIS_RESPONSE_HI = (
    "मुझे बहुत अच्छा लगा कि तुमने यह मुझसे कहा, वत्स। तुम्हारी यह पीड़ा सच में भारी है, और इसे "
    "अकेले उठाना ज़रूरी नहीं। अभी किसी सच्चे इंसान से बात करना — यह कमज़ोरी नहीं, सबसे बड़ा साहस है। "
    "कृपया अभी संपर्क करो — टेली-मानस 14416 (भारत, 24×7) या आसरा +91-9820466726। यदि तुम तुरंत ख़तरे "
    "में हो, तो 112 पर कॉल करो। मैं यहीं हूँ, तुम्हारे साथ। क्या तुम इस समय सुरक्षित हो?"
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


def crisis_payload() -> dict:
    return {"message": CRISIS_RESPONSE_HI, "helplines": HELPLINES}
