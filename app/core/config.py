"""Application settings (plan §9, §10). Env-overridable via SARATHI_* variables."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
CORPUS_DIR = BACKEND_DIR / "data" / "corpus" / "bhagavad_gita"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SARATHI_", env_file=".env", extra="ignore")

    app_name: str = "Sarathi"
    environment: str = "dev"

    # corpus
    corpus_dir: Path = CORPUS_DIR

    # --- LLM provider (plan §9) ---
    # "router" = OpenRouter→Ollama→(stub) failover chain; "stub" = deterministic, no network.
    llm_provider: str = "router"

    # OpenRouter (primary; Hindi-strong). is_configured iff api_key is set.
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model_strong: str = "qwen/qwen-2.5-72b-instruct"
    openrouter_model_cheap: str = "qwen/qwen-2.5-7b-instruct"

    # Ollama (fallback; local, Hindi-capable). DEGRADED mode (plan §9).
    # Disabled by default — enable once you have `ollama serve` running with the model pulled,
    # so dev without a daemon doesn't waste time on dead connections.
    ollama_enabled: bool = False
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    # Faithfulness auto-drop (plan §7.2). OFF by default: an LLM grading its own faithfulness is
    # fallible (esp. small/local models → false negatives that strip valid verses). The PRIMARY
    # defense is the human-reviewed theme_map. Enable only with a strong model + a validated
    # faithfulness golden set. When off, the verify node still drops invalid ids (structural).
    faithfulness_filter_enabled: bool = False

    # resilience
    request_timeout_s: float = 30.0
    max_retries: int = 2
    circuit_fail_threshold: int = 3
    circuit_reset_s: float = 20.0

    # caching (plan §10) — in-process response cache for now
    cache_enabled: bool = True
    cache_size: int = 512

    # --- storage / memory (plan §6) ---
    # Disabled by default → in-memory store (so it runs without a Mongo daemon).
    mongo_enabled: bool = False
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "sarathi"
    memory_recall_k: int = 3            # episodes injected into compose
    memory_retention_days: int = 90     # episodic retention (logged-in); enforce in prod

    # dev convenience: if no live provider is reachable, fall back to the deterministic stub
    # so the app still runs without keys. Set False in prod to surface real outages.
    allow_stub_fallback: bool = True

    # performance budget (plan §10.1) — set NOW, not later.
    latency_budget_p95_ms: int = 6000
    token_budget_per_turn: int = 4000

    # streaming
    stream_word_delay_ms: int = 12  # cosmetic pacing for the user-facing token stream


settings = Settings()
