"""Regression guard for the §7.2 MISAPPLICATION finding (triage 2026-06-24).

A "मन बेचैन रहता है, ध्यान नहीं लगता" (restless / overthinking mind) query was answered with
BG2.62 — the desire→attachment→anger cascade reserved for the क्रोध theme. That is a confident,
fluent, WRONG citation: the guidance ("control the mind, calm it gradually") matched 6.35's
teaching while the stapled verse said something else. Krishna's literal reply to this complaint is
BG6.35 (अभ्यासेन तु…वैराग्येण च गृह्यते). These tests pin that fix:

  • the verse now exists in the corpus,
  • the retriever leads with 6.35 (and does NOT lead with 2.62) for a restless-mind concern,
  • other themes still route correctly (no regression),
  • the practical-step separator survives streaming (the "…ले जाओ।आज का…" run-together bug).
"""

from __future__ import annotations

from app.graph.render import word_stream
from app.retrieval.corpus import get_corpus
from app.retrieval.pageindex import retrieve

RESTLESS = (
    "मेरा मन बहुत बेचैन रहता है। हर समय कुछ न कुछ सोचता रहता हूँ, "
    "रात को भी विचार रुकते नहीं, और किसी काम में शांति से ध्यान नहीं लगा पाता।"
)


def _ids(query: str) -> list[str]:
    return [v["id"] for v in retrieve(query, get_corpus())]


def test_corpus_has_the_restless_mind_verses():
    corpus = get_corpus()
    assert corpus.exists("BG6.35"), "BG6.35 (abhyāsa+vairāgya) must be in the corpus"
    assert corpus.exists("BG6.26"), "BG6.26 (bring the wandering mind back) must be in the corpus"


def test_restless_mind_leads_with_BG6_35_not_the_anger_verse():
    ids = _ids(RESTLESS)
    assert ids[0] == "BG6.35", f"restless mind must lead with BG6.35, got {ids}"
    # the anger-chain verse must not be the answer for a restless mind
    assert ids[0] != "BG2.62"
    assert "BG2.62" not in ids[:2], f"BG2.62 must not be a primary candidate here, got {ids}"


def test_other_themes_still_route_correctly():
    # anger genuinely belongs to BG2.62; the restless fix must not poach it
    assert _ids("किसी ने धोखा दिया और मेरा गुस्सा शांत नहीं हो रहा, बार-बार क्रोध आता है।")[0] == "BG2.62"
    assert _ids("मेरे पिता का देहांत हो गया, मैं स्वीकार नहीं कर पा रहा।")[0] == "BG2.20"
    assert _ids("समझ नहीं आता ज़िंदगी का क्या करूँ, सब आगे हैं मैं भटका हूँ।")[0] == "BG3.35"


def test_word_stream_preserves_leading_separator():
    # the "\n\n" prefix on the practical step / disclaimer must survive tokenisation,
    # otherwise it renders as "…ले जाओ।आज का छोटा कदम" (no break).
    toks = word_stream("\n\nआज का छोटा कदम: हर दिन")
    assert "".join(toks).startswith("\n\n"), "leading newlines must not be dropped"
