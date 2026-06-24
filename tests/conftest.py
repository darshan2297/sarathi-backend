"""Pytest isolation: pin a deterministic config BEFORE app modules import settings.

The test suite asserts deterministic stub behaviour. Without this, an ambient .env (e.g. with
SARATHI_OLLAMA_ENABLED=true) would make tests hit the live model — slow and non-deterministic.
Setting these env vars here (conftest is imported before tests) forces the stub + in-memory store.
"""

import os

os.environ["SARATHI_LLM_PROVIDER"] = "stub"
os.environ["SARATHI_OLLAMA_ENABLED"] = "false"
os.environ["SARATHI_MONGO_ENABLED"] = "false"
os.environ["SARATHI_FAITHFULNESS_FILTER_ENABLED"] = "false"
os.environ["SARATHI_ALLOW_STUB_FALLBACK"] = "true"  # the stub-fallback test depends on this
os.environ["SARATHI_STREAM_WORD_DELAY_MS"] = "0"
