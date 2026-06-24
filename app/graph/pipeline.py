"""Turn runner (plan §4, §10) — drives the LangGraph and streams the result.

We run the graph with `astream(stream_mode="updates")` so we can emit a `status` event as each agent
node finishes, then — once the answer is fully composed and the canonical verse injected — stream the
Hindi to the user word-by-word (we MUST inject before showing, per §7.1). Yields the WS event
protocol: meta · status · token · verse_card · done · error.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from app.core.budget import TurnBudget, latency_recorder
from app.core.config import settings
from app.core.metrics import metrics
from app.graph.build import build_graph
from app.graph.render import inject_verse, word_stream  # noqa: F401 (inject_verse re-exported)
from app.retrieval.corpus import get_corpus

_STATUS = {
    "input_guard": "सुन रहा हूँ",
    "understanding": "समझ रहा हूँ",
    "memory_recall": "तेरी यात्रा याद कर रहा हूँ",
    "retrieve": "ग्रंथों में देख रहा हूँ",
    "compose": "उत्तर रच रहा हूँ",
    "verify": "परख रहा हूँ",
}


async def run_turn(
    *,
    user_message: str,
    history: list[dict] | None = None,
    turn_id: str,
    user_id: str | None = None,
    tier: str = "guest",
    stream_delay_ms: int | None = None,
) -> AsyncIterator[dict]:
    history = history or []
    delay = (settings.stream_word_delay_ms if stream_delay_ms is None else stream_delay_ms) / 1000
    budget = TurnBudget(
        token_budget=settings.token_budget_per_turn,
        latency_budget_ms=settings.latency_budget_p95_ms,
    )
    corpus = get_corpus()

    try:
        initial = {
            "user_message": user_message,
            "thread_history": history,
            "turn_id": turn_id,
            "budget": budget,
            "user_id": user_id,
            "tier": tier,
        }
        final: dict = dict(initial)

        yield {"type": "meta", "turn_id": turn_id}

        async for chunk in build_graph().astream(initial, stream_mode="updates"):
            for node_name, delta in chunk.items():
                if isinstance(delta, dict):
                    final.update(delta)
                if node_name in _STATUS:
                    yield {"type": "status", "stage": _STATUS[node_name], "node": node_name}
                if node_name == "understanding":
                    yield {"type": "meta", "turn_id": turn_id, "mode": final.get("response_mode"),
                           "intent": final.get("intent"), "emotion": final.get("emotion")}

        rendered = final.get("rendered_text", "")
        verse_id = final.get("verse_id")
        verse_card = final.get("verse_card")
        safety = bool(final.get("safety_flag"))

        # crisis path: surface helplines up front (plan §8, §10 protocol)
        if safety and final.get("safety_payload"):
            yield {"type": "safety", **final["safety_payload"]}

        for tok in word_stream(rendered):
            if delay:
                await asyncio.sleep(delay)
            yield {"type": "token", "text": tok}

        if verse_card:
            yield {"type": "verse_card", **verse_card}

        if final.get("practical_step_hi"):
            for tok in word_stream(f"\n\nआज का छोटा कदम: {final['practical_step_hi']}"):
                if delay:
                    await asyncio.sleep(delay)
                yield {"type": "token", "text": tok}

        if final.get("disclaimer"):
            for tok in word_stream(f"\n\n{final['disclaimer']}"):
                if delay:
                    await asyncio.sleep(delay)
                yield {"type": "token", "text": tok}

        latency_recorder.record(budget.elapsed_ms)
        done = {
            "type": "done",
            "turn_id": turn_id,
            "mode": final.get("response_mode"),
            "verse_id": verse_id,
            "citation": corpus.citation(verse_id) if verse_id else None,
            "grounded": verse_id is not None,
            "verified": final.get("verified"),
            "safety": safety,
            "provider": final.get("provider"),
            "degraded": final.get("degraded", False),
            "budget": budget.summary(),
        }
        metrics.record_turn(done)
        yield done
    except Exception as exc:  # graceful error envelope (plan §10)
        yield {"type": "error", "turn_id": turn_id,
               "message": "क्षमा करना, वत्स — अभी कुछ बाधा आ गई।", "detail": str(exc)}
