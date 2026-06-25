"""Evaluation harness (plan §15).

Scores, against the golden set:
  • retrieval hit-rate  — does the retriever surface an expected verse?
  • safety routing      — do crisis messages trip crisis detection?
  • harm routing        — do harm-to-others messages trip refusal?
  • structural verse correctness — injection only ever emits corpus Sanskrit (100% by construction).

Deliberately NOT auto-scored here (honest, per plan §7.2 / §9):
  • FAITHFULNESS / MISAPPLICATION — needs a live LLM judge + human spot-check; an LLM grading itself
    is not ground truth. Reported as "needs LLM + human review".
  • FALLBACK quality — the Ollama degraded path must be judged against a SEPARATE, lower bar so the
    numbers don't lie about what users get during an outage. Reported as a distinct track.
"""

from __future__ import annotations

from app.eval.golden import GOLDEN
from app.graph.nodes.understanding import heuristic_understanding
from app.graph.render import inject_verse
from app.guardrails.crisis import detect_crisis, detect_harm_to_others
from app.retrieval.corpus import get_corpus
from app.retrieval.pageindex import retrieve


def _rate(passed: int, total: int) -> float:
    return round(100 * passed / total, 1) if total else 0.0


def structural_injection_ok() -> bool:
    """Verify injection emits canonical Sanskrit for a real id and nothing for a bogus one (§7.1)."""
    corpus = get_corpus()
    vid = "BG2.47"
    canonical = corpus.get_verse(vid)["sanskrit"].splitlines()[0].rstrip("।॥ ")
    rendered, card = inject_verse("एक सत्य — {{VERSE}}।", vid, corpus)
    ok_real = canonical in rendered and card and card["sanskrit"] == corpus.get_verse(vid)["sanskrit"]
    rendered2, card2 = inject_verse("एक सत्य — {{VERSE}}।", "BG99.99", corpus)
    ok_bogus = card2 is None and "«" not in rendered2
    return bool(ok_real and ok_bogus)


def run_eval(cases: list[dict] | None = None) -> dict:
    cases = cases or GOLDEN
    corpus = get_corpus()
    results: list[dict] = []

    for c in cases:
        msg = c["message"]
        if c.get("expect_safety"):
            results.append({"id": c["id"], "kind": "safety", "pass": detect_crisis(msg)})
        elif c.get("expect_harm"):
            results.append({"id": c["id"], "kind": "harm", "pass": detect_harm_to_others(msg)})
        elif c.get("expect_mode") or c.get("expect_no_crisis"):
            # routing guard (triage 2026-06-25), scored against the DETERMINISTIC heuristic — the
            # always-on safety net (a live model may sample differently, just as safety_routing pins
            # the keyword detector, not the LLM): out-of-scope professional advice must NOT trip the
            # crisis path and must reach the right response_mode (e.g. out_of_scope, not open).
            out = heuristic_understanding(msg)
            checks = []
            if c.get("expect_no_crisis"):
                checks.append(not detect_crisis(msg) and not out.get("safety_flag"))
            if c.get("expect_mode"):
                checks.append(out.get("response_mode") == c["expect_mode"])
            results.append({"id": c["id"], "kind": "routing", "pass": all(checks),
                            "expected_mode": c.get("expect_mode"),
                            "got_mode": out.get("response_mode"),
                            "crisis": bool(out.get("safety_flag") or detect_crisis(msg))})
        elif c.get("expect_verses"):
            ranked = [v["id"] for v in retrieve(msg, corpus)]
            got = set(ranked)
            lead = ranked[0] if ranked else None
            hit = bool(set(c["expect_verses"]) & got)
            # §7.2: a forbidden look-alike verse must never be the CITED (lead) verse.
            forbid = c.get("forbid_verses", [])
            forbidden_lead = lead in forbid
            results.append({"id": c["id"], "kind": "retrieval",
                            "pass": hit and not forbidden_lead,
                            "expected": c["expect_verses"], "got": ranked,
                            "forbid": forbid, "lead": lead})
        else:
            results.append({"id": c["id"], "kind": "offtopic", "pass": True})

    def rate_for(kind: str) -> dict:
        rows = [r for r in results if r["kind"] == kind]
        return {"passed": sum(r["pass"] for r in rows), "total": len(rows),
                "rate_pct": _rate(sum(r["pass"] for r in rows), len(rows))}

    return {
        "results": results,
        "summary": {
            "retrieval": rate_for("retrieval"),
            "safety_routing": rate_for("safety"),
            "harm_routing": rate_for("harm"),
            "scope_routing": rate_for("routing"),
            "structural_injection_ok": structural_injection_ok(),
        },
        "not_auto_scored": {
            "faithfulness_misapplication": "needs live LLM judge + human spot-check (plan §7.2)",
            "fallback_quality": "judge Ollama path against a SEPARATE lower bar (plan §9)",
        },
    }
