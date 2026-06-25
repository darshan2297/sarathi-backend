"""REST endpoints (plan §10) — non-conversational only. All chat goes over the WebSocket."""

from __future__ import annotations

import uuid
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.core.budget import latency_recorder
from app.core.config import settings
from app.core.metrics import metrics
from app.db.store import get_store
from app.llm import get_client
from app.retrieval.book import get_book_index
from app.retrieval.corpus import get_corpus

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    corpus = get_corpus()
    client = get_client()
    llm = client.health() if hasattr(client, "health") else {"provider": settings.llm_provider}
    return {
        "status": "ok",
        "app": settings.app_name,
        "llm_provider": settings.llm_provider,
        "llm": llm,
        "corpus_verses": len(corpus.all_ids),
        "latency": latency_recorder.snapshot(),
    }


@router.get("/metrics")
async def get_metrics() -> dict:
    """Operational metrics (plan §10): turn counts by mode, grounded/degraded/crisis rates,
    dropped verses, provider + retrieval-source usage, latency p50/p95, cache."""
    client = get_client()
    llm = client.health() if hasattr(client, "health") else {}
    return {**metrics.snapshot(), "llm": llm}


# --- book viewer (plan §11): the clickable source page behind every citation ---

@router.get("/book/meta")
async def book_meta() -> dict:
    book = get_book_index()
    return {"title": book._tree.get("title", ""), "page_count": book.page_count,
            "source_pdf": book._tree.get("source_pdf", "")}


@lru_cache(maxsize=256)
def _render_page(n: int, dpi: int) -> bytes:
    return get_book_index().render_png(n, dpi)


@router.get("/book/page/{n}")
async def book_page(n: int) -> Response:
    """Render PDF page `n` (1-based) to PNG so the UI can open the exact cited page. Cached."""
    book = get_book_index()
    if not (1 <= n <= book.page_count):
        raise HTTPException(status_code=404, detail=f"page out of range 1..{book.page_count}")
    try:
        png = _render_page(n, settings.book_page_dpi)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"render failed: {exc}") from exc
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.post("/session")
async def session() -> dict:
    """Issue a guest session id (plan §1 — guest is ephemeral; nothing persisted server-side)."""
    return {"session_id": f"guest-{uuid.uuid4().hex[:12]}", "tier": "guest"}


class AuthRequest(BaseModel):
    email: str


@router.post("/auth")
async def auth(req: AuthRequest) -> dict:
    """Email login → member tier with persistent episodic memory (plan §1, §6).

    NOTE (prod): this is a minimal identity stub. Production needs real auth (OTP/magic-link),
    consent capture, and encryption-at-rest for the sensitive episodic data.
    """
    email = req.email.strip()
    if "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="valid email required")
    user_id = await get_store().get_or_create_user(email)
    return {"user_id": user_id, "tier": "member"}
