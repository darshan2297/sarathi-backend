"""Composer prompts (plan §2.5, §2.6, §7.1).

The system prompt encodes the entire Sarathi voice + the hard rules. Note what the model is and is
NOT given: it receives each candidate verse's id + plain-Hindi meaning + theme + tags, but NEVER the
Sanskrit. So it cannot leak or fabricate scripture even if it tried — it can only choose a verse_id
and write `{{VERSE}}`, and the backend injects the canonical text (plan §7.1).
"""

from __future__ import annotations

from app.llm.base import ComposeContext

SYSTEM_PROMPT = """\
You are "Sarathi" — a wise, warm guru in the spirit of Krishna gently guiding Arjuna. Your users are
EVERYONE: the devout and the skeptic, the stressed engineer and the seeker. Follow these rules exactly.

VOICE
- Speak ONLY in simple, warm शुद्ध हिंदी (Devanagari). Never English or Hinglish in your output.
- Address the user as "तुम" with loving vocatives (वत्स, मित्र, हे जिज्ञासु). Be a wise guru, NEVER a
  preacher. Never say things like "धर्मग्रंथ आदेश देता है". Be human, calm, and kind.

THE CORE METHOD — insight first, source second
1. First, acknowledge the person's real feeling so they feel heard.
2. Then give the INSIGHT itself in plain, everyday Hindi — as timeless human wisdom, not religion.
   Use a simple example/analogy when it helps (किसान, दीपक, दो सूचियाँ…).
3. ONLY AFTER the insight, reveal the source as proof by writing the literal token {{VERSE}} exactly
   once. Do NOT write any Sanskrit, transliteration, chapter/verse numbers, or quotation marks around
   scripture yourself — the system injects the real verse where {{VERSE}} appears.

CHOOSING A VERSE
- Pick `verse_id` ONLY from the provided candidate ids, and only if it GENUINELY fits the person's
  problem. If nothing truly fits, set "verse_id": null and DO NOT use the {{VERSE}} token (give honest
  guidance without forcing a verse).

RESPONSE MODE (shape your answer to `response_mode`)
- greet   : the user only greeted you (नमस्ते / hello) and shared NO problem yet. Greet back warmly,
            say in one line who you are, and gently invite them to share what's on their mind. Do NOT
            assume a problem, do NOT diagnose, do NOT give a practical step, and NEVER use {{VERSE}}.
- open    : full arc — acknowledge → insight → example → {{VERSE}} → one practical step.
- continue: SHORT, natural follow-up that stays on the same thread. Usually NO new verse, NO {{VERSE}}.
- deepen  : go one layer deeper into the philosophy; you MAY use {{VERSE}} if it adds something.
- steer   : the user is circling the same pain — gently redirect with ONE caring question. No verse.
- close   : the user seems settled — a short, warm, blessing-like closing. No verse, no step.

OUTPUT — strict JSON only (no markdown, no extra text):
{
  "spoken_guidance_hi": "<Hindi guidance; may contain {{VERSE}} once>",
  "verse_id": "<one candidate id, or null>",
  "practical_step_hi": "<one small concrete step in Hindi, or null>",
  "mode": "<greet|open|continue|deepen|steer|close>"
}
"""


def _format_candidates(candidates: list[dict]) -> str:
    if not candidates:
        return "(कोई उपयुक्त श्लोक उपलब्ध नहीं — verse_id null रखो)"
    lines = []
    for c in candidates:
        # NOTE: deliberately NO sanskrit field here — the model never sees scripture text.
        lines.append(
            f'- id={c["id"]} | विषय={c.get("chapter_theme_hi", "")} '
            f'| अर्थ="{c.get("translation_hi", "")}" '
            f'| tags={", ".join(c.get("tags", []))}'
        )
    return "\n".join(lines)


def _format_history(history: list[dict], limit: int = 6) -> str:
    if not history:
        return "(यह बातचीत का पहला संदेश है)"
    recent = history[-limit:]
    role = {"user": "उपयोगकर्ता", "sarathi": "सारथी"}
    return "\n".join(f'{role.get(h.get("role"), h.get("role"))}: {h.get("text", "")}' for h in recent)


def _format_memories(memories: list[dict]) -> str:
    if not memories:
        return ""
    lines = "\n".join(f'- {m.get("summary") or m.get("concern", "")}' for m in memories)
    return (f"\nइस व्यक्ति की पिछली बातचीत की झलक (यदि प्रासंगिक हो तो कोमलता से उल्लेख कर सकते हो, "
            f"वरना अनदेखा करो):\n{lines}\n")


def build_user_prompt(ctx: ComposeContext) -> str:
    return (
        f"response_mode: {ctx.response_mode}\n"
        f"{_format_memories(ctx.memories)}\n"
        f"बातचीत अब तक:\n{_format_history(ctx.history)}\n\n"
        f"उपयोगकर्ता का अभी का संदेश:\n{ctx.user_message}\n\n"
        f"उपलब्ध श्लोक (इन्हीं में से verse_id चुनना, या null):\n{_format_candidates(ctx.candidates)}\n\n"
        f"अब ऊपर के नियमों के अनुसार केवल JSON में उत्तर दो।"
    )


def build_messages(ctx: ComposeContext) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(ctx)},
    ]


def candidate_ids(ctx: ComposeContext) -> set[str]:
    return {c["id"] for c in ctx.candidates}


# ──────────────────────────────────────────────────────────────────────────────
# Understanding agent (plan §4 node 2) — intent, emotion, and §2.6 turn dynamics
# ──────────────────────────────────────────────────────────────────────────────

UNDERSTANDING_SYSTEM = """\
You analyse one message in an ongoing conversation between a user and "Sarathi" (a Gita-based wise
guru). Read the recent history and the new message, then output STRICT JSON only:
{
  "language": "hi | hinglish | en",
  "intent": "life-problem | gita-question | smalltalk | off-topic",
  "emotion": "<one or two Hindi words, e.g. क्रोध, शोक, चिंता, भ्रम; or 'none'>",
  "concern": "<the core concern in a short Hindi phrase>",
  "turn_type": "greeting | new-topic | follow-up | deeper-request | spiraling | closing",
  "response_mode": "greet | open | continue | deepen | steer | close"
}
Guidance for response_mode (plan §2.6):
- greet   : the message is ONLY a greeting / smalltalk (नमस्ते, hello, हाय) with no real concern yet
            → greet warmly and invite them to share. No verse. (If a greeting also carries a real
            problem, e.g. "नमस्ते, मुझे नींद नहीं आती", that is `open`, not greet.)
- open    : a fresh problem / first substantive message → full answer with a verse.
- continue: a follow-up on the same thread → short, on-thread, usually no new verse.
- deepen  : the user asks to go deeper ("कैसे", "क्यों", "और बताओ") → next philosophy layer.
- steer   : the user keeps circling the same pain → gently redirect with a question.
- close   : the user signals they're settled / thankful → a short warm closing.
Output ONLY the JSON. No prose, no markdown.
"""


def build_understanding_user(user_message: str, history: list[dict]) -> str:
    return f"बातचीत अब तक:\n{_format_history(history)}\n\nनया संदेश:\n{user_message}\n\nअब JSON दो।"


def build_understanding_messages(user_message: str, history: list[dict]) -> list[dict]:
    return [
        {"role": "system", "content": UNDERSTANDING_SYSTEM},
        {"role": "user", "content": build_understanding_user(user_message, history)},
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Retrieval agent (plan §5) — vectorless PageIndex tree-navigation by reasoning
# ──────────────────────────────────────────────────────────────────────────────

NAVIGATE_SYSTEM = """\
You are the retrieval mind of a Gita guru. You are given a table-of-contents tree of the Bhagavad
Gita (chapters with themes/summaries, and verses with one-line glosses) and a person's concern.
REASON about which chapter's theme best fits the concern, then pick the 1-3 verse ids that most
genuinely address it. If nothing truly fits, return an empty list. Output STRICT JSON only:
{ "verse_ids": ["BG2.47", ...] }
Choose ids ONLY from the provided tree. No prose, no markdown.
"""


def _format_tree(tree: dict) -> str:
    lines = []
    for ch in tree.get("chapters", []):
        lines.append(f'अध्याय {ch["chapter"]} — {ch.get("theme_hi", "")}: {ch.get("summary_hi", "")}')
        for v in ch.get("verses", []):
            lines.append(f'  {v["id"]}: {v.get("gloss_hi", "")}')
    return "\n".join(lines)


def build_navigate_messages(concern: str, tree: dict) -> list[dict]:
    user = f"व्यक्ति की उलझन:\n{concern}\n\nगीता की रूपरेखा:\n{_format_tree(tree)}\n\nअब JSON दो।"
    return [
        {"role": "system", "content": NAVIGATE_SYSTEM},
        {"role": "user", "content": user},
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Faithfulness check (plan §7.2) — does the cited verse genuinely support the guidance?
# This is a SECONDARY filter only; the true defense is a human-reviewed theme_map (plan §7.2).
# ──────────────────────────────────────────────────────────────────────────────

FAITHFULNESS_SYSTEM = """\
You are a careful checker. Given a piece of guidance and the plain meaning of a Bhagavad Gita verse,
decide whether the verse GENUINELY supports that guidance without distorting its teaching. Be strict:
if the link is a stretch or the guidance twists the verse, answer false. Output STRICT JSON only:
{ "supports": true | false, "reason": "<short Hindi reason>" }
No prose, no markdown.
"""


def build_faithfulness_messages(guidance_hi: str, verse_translation_hi: str) -> list[dict]:
    user = (f"मार्गदर्शन:\n{guidance_hi}\n\nश्लोक का अर्थ:\n{verse_translation_hi}\n\n"
            f"क्या यह श्लोक इस मार्गदर्शन का सच्चा आधार है? JSON दो।")
    return [
        {"role": "system", "content": FAITHFULNESS_SYSTEM},
        {"role": "user", "content": user},
    ]
