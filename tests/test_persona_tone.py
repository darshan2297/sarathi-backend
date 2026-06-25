"""Persona/tone prompt guards (QA M-1 register, M-2 metaphor crutch, M-3 address, L-2 grammar;
triage 2026-06-25).

These are LLM-behaviour issues with no deterministic output to assert, so the regression guard is on
the composer SYSTEM_PROMPT itself — the single lever. They fail if the tone/persona guidance is
dropped or if the old metaphor-seeding crutch is reintroduced.
"""

from __future__ import annotations

from app.llm.prompts import SYSTEM_PROMPT


def test_metaphor_crutch_seed_is_removed():
    # the old prompt literally seeded the recurring images: "...analogy when it helps (किसान, दीपक…)".
    # That seed must be gone; instead the prompt must warn against over-reusing those stock metaphors.
    assert "when it helps (किसान" not in SYSTEM_PROMPT
    assert "QA M-2" in SYSTEM_PROMPT
    assert "FRESH image" in SYSTEM_PROMPT


def test_register_calibration_guidance_present():
    assert "QA M-1" in SYSTEM_PROMPT
    assert "MATCH YOUR REGISTER TO THE WEIGHT" in SYSTEM_PROMPT


def test_consistent_address_guidance_present():
    assert "QA M-3" in SYSTEM_PROMPT
    assert "ONE consistent term" in SYSTEM_PROMPT
    assert "हे जिज्ञासु" in SYSTEM_PROMPT          # named as the vocative to AVOID


def test_clean_grammar_guidance_present():
    assert "QA L-2" in SYSTEM_PROMPT
