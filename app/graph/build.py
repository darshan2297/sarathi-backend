"""LangGraph wiring (plan §4, §8). Compiles the Sarathi multi-agent graph.

    input_guard ──crisis?──▶ crisis_response ─┐
         │ continue                           ├─▶ output_guard ─▶ END
         ▼                                     │
    understanding → retrieve → compose → verify → output ─┘

Memory recall/write nodes slot in at Phase 5 without disturbing this path.
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.graph.nodes.compose import compose_node
from app.graph.nodes.guards import crisis_response_node, input_guard_node, output_guard_node
from app.graph.nodes.memory import memory_recall_node, memory_write_node
from app.graph.nodes.output import output_node
from app.graph.nodes.retrieval import retrieval_node
from app.graph.nodes.understanding import understanding_node
from app.graph.nodes.verify import verify_node
from app.graph.state import GraphState


def _route_after_input(state: GraphState) -> str:
    return "crisis" if state.get("safety_flag") else "continue"


@lru_cache(maxsize=1)
def build_graph():
    g = StateGraph(GraphState)
    g.add_node("input_guard", input_guard_node)
    g.add_node("crisis_response", crisis_response_node)
    g.add_node("understanding", understanding_node)
    g.add_node("memory_recall", memory_recall_node)
    g.add_node("retrieve", retrieval_node)
    g.add_node("compose", compose_node)
    g.add_node("verify", verify_node)
    g.add_node("output", output_node)
    g.add_node("output_guard", output_guard_node)
    g.add_node("memory_write", memory_write_node)

    g.add_edge(START, "input_guard")
    g.add_conditional_edges(
        "input_guard", _route_after_input,
        {"crisis": "crisis_response", "continue": "understanding"},
    )
    g.add_edge("crisis_response", "output_guard")
    g.add_edge("understanding", "memory_recall")
    g.add_edge("memory_recall", "retrieve")
    g.add_edge("retrieve", "compose")
    g.add_edge("compose", "verify")
    g.add_edge("verify", "output")
    g.add_edge("output", "output_guard")
    g.add_edge("output_guard", "memory_write")
    g.add_edge("memory_write", END)
    return g.compile()
