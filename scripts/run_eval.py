#!/usr/bin/env python3
"""Run the golden evaluation and print a report (plan §15).  Usage:  python scripts/run_eval.py"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `app` importable

from app.eval.harness import run_eval  # noqa: E402


def main() -> None:
    report = run_eval()
    s = report["summary"]

    print("\n🕉️  सारथी — Golden Evaluation\n" + "─" * 48)
    for r in report["results"]:
        mark = "✓" if r["pass"] else "✗"
        extra = ""
        if r["kind"] == "retrieval":
            extra = f"  expected~{r['expected']} got {r['got']}"
            if r.get("forbid"):
                extra += f"  forbid={r['forbid']} (lead={r['lead']})"
        elif r["kind"] == "routing":
            extra = f"  mode={r['got_mode']} (expected {r['expected_mode']}), crisis={r['crisis']}"
        print(f"  {mark} [{r['kind']:<9}] {r['id']}{extra}")

    print("─" * 48)
    print(f"  retrieval hit-rate : {s['retrieval']['rate_pct']}%  "
          f"({s['retrieval']['passed']}/{s['retrieval']['total']})")
    print(f"  safety routing     : {s['safety_routing']['rate_pct']}%  "
          f"({s['safety_routing']['passed']}/{s['safety_routing']['total']})")
    print(f"  harm routing       : {s['harm_routing']['rate_pct']}%  "
          f"({s['harm_routing']['passed']}/{s['harm_routing']['total']})")
    print(f"  scope routing      : {s['scope_routing']['rate_pct']}%  "
          f"({s['scope_routing']['passed']}/{s['scope_routing']['total']})")
    print(f"  verse injection    : {'OK (canonical, structural)' if s['structural_injection_ok'] else 'FAIL'}")

    print("\n  Not auto-scored (honest — plan §7.2 / §9):")
    for k, v in report["not_auto_scored"].items():
        print(f"    • {k}: {v}")
    print("\n  ⚠️  theme_map + this golden set require Gita-literate review before launch.\n")


if __name__ == "__main__":
    main()
