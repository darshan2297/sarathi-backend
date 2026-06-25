"""Verse-relevance regression guard (QA H-4 missing/irrelevant verse, H-5 BG6.35 over-default,
triage 2026-06-25).

The bugs and their root causes (confirmed by live tracing):
  • RC3 — retrieval ran ONLY on the understanding model's `concern`, which is often lossy or
    mistranslated ("comparison/purpose" → "किस्मत की चाह"; "brother" → "बROTHER"), sending it to the
    wrong verse. Fix: retrieve on the raw user words + the concern together.
  • RC2 — merge ranked the LLM navigator ABOVE the reviewed theme_map, so it buried correct curated
    picks (e.g. BG2.47/2.48 for fear of failure). Fix: strong → curated → navigator → gloss.
  • Theme gap — "fear of failure" had no trigger in the anxiety-about-results theme. Fix: added
    failure phrasings to that EXISTING theme (verses BG2.47/2.48 unchanged).

These pin the deterministic (LLM-free) layer; the navigator only widens beyond it.
"""

from __future__ import annotations

import asyncio

from app.core.budget import TurnBudget
from app.graph.nodes.retrieval import retrieval_node
from app.retrieval.corpus import get_corpus
from app.retrieval.pageindex import retrieve


def _budget():
    return TurnBudget(4000, 6000)


def _ids(query: str) -> list[str]:
    return [v["id"] for v in retrieve(query, get_corpus(), k=3)]


def _node_ids(user_message: str, concern: str) -> list[str]:
    out = asyncio.run(retrieval_node(
        {"user_message": user_message, "concern": concern,
         "response_mode": "open", "budget": _budget()}))
    return [c["id"] for c in out["candidates"]]


# --- H-4: the named on-topic questions now surface a relevant verse -------------------------------

def test_fear_of_failure_maps_to_outcome_detachment_not_grief():
    for msg in ("मुझे अपनी नौकरी में असफल होने का बहुत डर है",
                "मेहनत के बाद भी असफलता का डर सताता है",
                "I am terrified of failing at my job"):
        ids = _ids(msg)
        assert ids and ids[0] in ("BG2.47", "BG2.48"), f"{msg} -> {ids}"
        assert "BG2.20" not in ids[:2], f"grief verse mis-cited for fear of failure: {ids}"


def test_jealousy_anger_maps_to_anger_chain_not_restless_mind():
    ids = _ids("दूसरों की सफलता देख मुझे जलन और गुस्सा होता है")
    assert ids[0] in ("BG2.62", "BG2.63"), ids
    assert "BG6.35" not in ids[:2], f"restless-mind verse over-defaulted for anger: {ids}"


# --- RC3: the raw message drives retrieval even when the concern is lossy/vague --------------------

def test_retrieval_uses_raw_message_when_concern_is_lossy():
    # a vague paraphrase that alone would NOT surface the anger verse — the raw words must rescue it
    ids = _node_ids("किसी ने मुझे धोखा दिया और मुझे बहुत गुस्सा आता है", concern="मन की उलझन")
    assert ids and ids[0] == "BG2.62", ids


def test_retrieval_node_grounds_when_concern_empty():
    # concern may be empty/None; retrieval must still ground from the message (no silent no-verse)
    ids = _node_ids("मेरे पिता का देहांत हो गया, मैं स्वीकार नहीं कर पा रहा", concern="")
    assert "BG2.20" in ids, ids


# --- H-5 regression: restless-mind verse must NOT poach other themes (still leads its own) ---------

def test_restless_mind_still_leads_its_own_theme():
    ids = _ids("मेरा मन बहुत बेचैन रहता है, हर समय सोचता रहता हूँ, ध्यान नहीं लगता")
    assert ids[0] == "BG6.35", ids
