"""Deterministic stub composer (Phase 1 only).

No network, no API key — lets us prove the full retrieve→compose→inject→stream loop and the
budget plumbing before the real LLM exists. It honours the real contract exactly:
  • outputs warm Hindi guidance, addressing the user as "तुम/वत्स" (plan: decided)
  • writes {{VERSE}} where the source reveal goes — NEVER any Sanskrit (plan §7.1)
  • shapes the answer by response_mode (open/continue/deepen/steer/close — plan §2.6)

Phase 2 replaces this with the OpenRouter↔Ollama router behind the same LLMClient interface.
"""

from __future__ import annotations

from app.core.budget import TurnBudget
from app.llm.base import VERSE_PLACEHOLDER, ComposeContext, ComposeResult

# theme → (acknowledgement, insight, practical step) — keyed off candidate tags / keywords.
_THEME_TEXT = {
    "anger": (
        "जिस पर हमने भरोसा किया, उसी का व्यवहार सबसे गहरी चोट देता है",
        "यह क्रोध तेरी कमज़ोरी नहीं, बस एक आग है जो अभी तेरी ही शांति जला रही है — और शांति लौटाना तेरे ही हाथ में है",
        "आज जब क्रोध उठे, स्वयं से कह — 'मैं अपनी शांति किसी और के व्यवहार से नहीं बाँधूँगा'",
    ),
    "grief": (
        "जिसे हम प्रेम करते हैं उसका जाना पूरे संसार को बदल देता है",
        "तेरा यह न-स्वीकार पाना दुर्बलता नहीं — वह प्रेम है जिसे अभी कोई ठिकाना नहीं मिल रहा",
        "हर दिन एक छोटा काम उनकी स्मृति में कर — पीड़ा धीरे-धीरे साथ रखने का मार्ग बन जाएगी",
    ),
    "anxiety": (
        "भविष्य का वह डर जो रातों की नींद चुरा लेता है, मैं समझता हूँ",
        "तेरी मेहनत तेरे हाथ में है, पर परिणाम अनेक कारणों से बनता है — उसी पकड़ ने तेरी नींद बाँध रखी है",
        "आज पूरे मन से अपना काम कर, और सोने से पहले कह — 'मेहनत मेरी, परिणाम मैं छोड़ता हूँ'",
    ),
    "purpose": (
        "यह लगना कि सब आगे हैं और मैं ही भटका हूँ, जितना भारी है उतना ही सबको लगता है",
        "जिन्हें तू 'तय' समझ रहा है, वे भी भीतर उतने ही अनिश्चित हैं — दूसरों से तुलना एक जाल है",
        "इस सप्ताह बस यह पूछ — 'यदि कोई न देख रहा हो, तो मैं किस काम में मन से समय दूँगा?'",
    ),
    "restless": (
        "मन का यूँ हर समय दौड़ते रहना और कहीं टिक न पाना सचमुच थका देता है",
        "मन चंचल है, यह सच है — पर यह कोई दोष नहीं; जैसे कोई भी कौशल अभ्यास से सधता है, "
        "वैसे ही मन भी धीरे-धीरे अभ्यास और थोड़ी अनासक्ति से शांत होना सीख जाता है",
        "आज दिन में एक छोटा समय तय कर — बस पाँच मिनट एक जगह बैठ, साँस पर ध्यान रख; "
        "मन भटके तो बिना झुँझलाए उसे कोमलता से वापस ले आ। यही 'अभ्यास' है",
    ),
}
_DEFAULT_TEXT = (
    "तेरे मन की बात मैं सुन रहा हूँ, वत्स",
    "थोड़ा रुक कर, इस उलझन को थोड़ी दूरी से देखना अक्सर रास्ता खोल देता है",
    "आज एक छोटा, सच्चा कदम चुन — बड़ा निर्णय बाद में अपने आप स्पष्ट होगा",
)

# out_of_scope (plan §8): gently decline the literal professional-advice ask, tailored to the domain,
# then the composer reframes to the in-scope concern below. NEVER names a stock / drug / legal opinion.
_OUT_OF_SCOPE_DECLINE = {
    "financial": "वत्स, कौन-सा शेयर खरीदना है या पैसा कहाँ लगाना है — यह सलाह देना मेरा काम नहीं।",
    "medical": "वत्स, कौन-सी दवा या इलाज लेना है — यह बताना मेरा काम नहीं; इसके लिए किसी योग्य चिकित्सक से मिलना।",
    "legal": "वत्स, क़ानूनी सलाह देना मेरा काम नहीं; इसके लिए किसी योग्य अधिवक्ता से बात करना।",
    "other": "वत्स, इस तरह का व्यावहारिक/विशेषज्ञ निर्णय बताना मेरा काम नहीं।",
}
_OUT_OF_SCOPE_FINANCIAL = ("invest", "stock", "share", "mutual fund", "crypto", "bitcoin",
                           "portfolio", "trading", "शेयर", "निवेश", "पैसा", "पैसे")
_OUT_OF_SCOPE_MEDICAL = ("medicine", "medical", "diagnos", "treatment", "symptom", "dosage",
                         "दवा", "इलाज", "खुराक", "बीमारी")
_OUT_OF_SCOPE_LEGAL = ("legal", "lawsuit", "sue", "court", "मुकदमा", "कानूनी", "क़ानूनी", "केस")


def _decline_for(user_message: str) -> str:
    low = user_message.lower()
    if any(w in low for w in _OUT_OF_SCOPE_FINANCIAL):
        return _OUT_OF_SCOPE_DECLINE["financial"]
    if any(w in low for w in _OUT_OF_SCOPE_MEDICAL):
        return _OUT_OF_SCOPE_DECLINE["medical"]
    if any(w in low for w in _OUT_OF_SCOPE_LEGAL):
        return _OUT_OF_SCOPE_DECLINE["legal"]
    return _OUT_OF_SCOPE_DECLINE["other"]


def _theme_for(ctx: ComposeContext) -> str:
    blob = " ".join(ctx.candidates and ctx.candidates[0].get("tags", []) or []) + " " + ctx.user_message
    blob = blob.lower()
    if any(w in blob for w in ("क्रोध", "गुस्सा", "धोखा", "anger", "betray")):
        return "anger"
    if any(w in blob for w in ("शोक", "देहांत", "मृत्यु", "grief", "death", "loss")):
        return "grief"
    # restless/overthinking mind — check before anxiety so "बेचैन/ध्यान नहीं लगता" lands on
    # the चंचल-मन teaching (अभ्यास+वैराग्य, BG6.35), not the outcome-anxiety branch (plan §7.2).
    if any(w in blob for w in ("बेचैन", "चंचल", "अस्थिर", "एकाग्र", "अभ्यास", "वैराग्य",
                               "भटक", "restless", "focus", "overthink", "concentrat", "wandering")):
        return "restless"
    if any(w in blob for w in ("चिंता", "डर", "नींद", "anxiety", "fear", "promotion", "परिणाम")):
        return "anxiety"
    if any(w in blob for w in ("दिशा", "भटक", "उद्देश्य", "purpose", "lost", "तुलना")):
        return "purpose"
    return "default"


class StubLLM:
    async def compose(self, ctx: ComposeContext, budget: TurnBudget) -> ComposeResult:
        theme = _theme_for(ctx)
        ack, insight, step = _THEME_TEXT.get(theme, _DEFAULT_TEXT)
        verse_id = ctx.candidates[0]["id"] if ctx.candidates else None

        # journey recall (member tier) — reference a past episode if we have one
        mem_prefix = ""
        if ctx.memories:
            past = ctx.memories[0].get("concern") or ctx.memories[0].get("summary") or ""
            if past:
                mem_prefix = f"पिछली बार तूने {past} की बात की थी, वत्स — मैं वह याद रखता हूँ। "

        mode = ctx.response_mode
        if mode == "greet":
            # Someone just said hello — greet back warmly, name who we are, invite them to share.
            # No verse, no diagnosis, no step. Returning members get a gentle welcome-back. (plan §2.6)
            if mem_prefix:
                text = (
                    "फिर से नमस्ते, वत्स। 🙏 तुझे यहाँ देखकर अच्छा लगा। "
                    "मन में जो भी चल रहा हो, बेझिझक कह — मैं सुन रहा हूँ।"
                )
            else:
                text = (
                    "नमस्ते वत्स। 🙏 मैं सारथी हूँ। मन में जो भी हो — कोई उलझन, कोई प्रश्न, "
                    "या बस एक भार — नि:संकोच कह। मैं यहीं हूँ, सुनने के लिए।"
                )
            text, verse_id, step = mem_prefix + text, None, None
        elif mode == "out_of_scope":
            # Decline the literal professional-advice ask, then reframe to the deeper, in-scope
            # concern (fear of the future / attachment to outcomes) and anchor it to a verse if one
            # was retrieved for that concern. Never give the surface advice (no stock/drug/legal pick).
            decline = _decline_for(ctx.user_message)
            if verse_id:
                text = (
                    f"{decline} पर तेरे प्रश्न के पीछे जो है — कल का डर, सुरक्षा की चाह — "
                    f"उस पर गीता ज़रूर कुछ कहती है, वत्स। {insight}। "
                    f"एक सत्य जो युगों से सहारा देता आया है — {VERSE_PLACEHOLDER}।"
                )
            else:
                text = (
                    f"{decline} पर इसके पीछे जो मन की उलझन है — कल का डर, परिणाम की चिंता — "
                    f"उस पर हम ज़रूर बात कर सकते हैं, वत्स। {insight}।"
                )
        elif mode == "close":
            text, verse_id, step = ("तेरे भीतर यह शांति बनी रहे, वत्स। 🙏", None, None)
        elif mode == "steer":
            text, verse_id, step = (
                f"हम इस पीड़ा की बात कर चुके हैं, वत्स। एक प्रश्न अपने लिए — यदि परिस्थिति कभी न बदले, "
                f"तो तेरे लिए शांति कैसी दिखेगी?",
                None,
                None,
            )
        elif mode == "continue":
            text = f"समझता हूँ, वत्स। {insight}।"
            verse_id = None  # follow-ups stay short, no reflex verse (plan §2.6)
        elif mode == "deepen" and verse_id:
            text = f"{mem_prefix}अब थोड़ा गहराई में चलें, वत्स। {insight}। और यही बात ऋषियों ने इस तरह कही — {VERSE_PLACEHOLDER}।"
        else:  # open (or deepen with no verse)
            if verse_id:
                text = (
                    f"{mem_prefix}वत्स, {ack}। {insight}। "
                    f"एक सत्य जो युगों से मनुष्य को सहारा देता आया है — {VERSE_PLACEHOLDER}।"
                )
            else:
                text = f"{mem_prefix}वत्स, {ack}। {insight}।"

        result = ComposeResult(
            spoken_guidance_hi=text,
            verse_id=verse_id,
            practical_step_hi=step,
            mode=mode,
        )

        # budget: simulate a realistic prompt + the produced output
        prompt = f"[compose:{mode}] {ctx.user_message} | candidates={[c['id'] for c in ctx.candidates]}"
        budget.add_call(prompt, text + (step or ""))
        return result
