"""Sarathi backend — FastAPI app (plan §10). WebSocket-first, async.

Run:  uvicorn app.main:app --reload  (from backend/)
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes, ws
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.retrieval.corpus import get_corpus

log = get_logger("sarathi")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    corpus = get_corpus()  # fail fast if the corpus is missing/broken
    log.info("startup", app=settings.app_name, provider=settings.llm_provider,
             verses=len(corpus.all_ids))
    yield
    log.info("shutdown")


app = FastAPI(title=f"{settings.app_name} API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before any deploy
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router)
app.include_router(ws.router)


@app.get("/")
async def root() -> dict:
    return {"app": settings.app_name, "ws": "/ws/chat", "health": "/health"}
