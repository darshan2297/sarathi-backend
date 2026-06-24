"""WebSocket /ws/chat (plan §10) — the primary, real-time chat transport.

Client → server : {"type":"user_message", "session_id": "...", "text": "..."}
Server → client : streamed typed events (meta/status/token/verse_card/done/error) from the pipeline.

Conversation (thread) history is held in memory for the life of the connection — this is the
guest tier (plan §1, §6): nothing is persisted; on disconnect/refresh it is gone.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.logging import get_logger
from app.db.store import get_store
from app.graph.pipeline import run_turn

router = APIRouter()
log = get_logger("sarathi.ws")


@router.websocket("/ws/chat")
async def chat(ws: WebSocket) -> None:
    await ws.accept()
    history: list[dict] = []          # ephemeral thread memory (both tiers)
    user_id: str | None = None        # set on auth → enables persistent episodic memory
    tier = "guest"
    try:
        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type")

            if mtype == "auth":
                email = (msg.get("email") or "").strip()
                if not email or "@" not in email:
                    await ws.send_json({"type": "error", "message": "valid email required"})
                    continue
                user_id = await get_store().get_or_create_user(email)
                tier = "member"
                log.info("authed", user_id=user_id)
                await ws.send_json({"type": "authed", "user_id": user_id, "tier": tier})
                continue

            if mtype != "user_message":
                await ws.send_json({"type": "error", "message": "unsupported message type"})
                continue

            user_text = (msg.get("text") or "").strip()
            if not user_text:
                await ws.send_json({"type": "error", "message": "empty message"})
                continue

            turn_id = uuid.uuid4().hex[:8]
            answer_parts: list[str] = []

            async for ev in run_turn(user_message=user_text, history=history, turn_id=turn_id,
                                     user_id=user_id, tier=tier):
                if ev["type"] == "token":
                    answer_parts.append(ev["text"])
                if ev["type"] == "done":
                    log.info("turn", turn_id=turn_id, tier=tier, mode=ev.get("mode"),
                             provider=ev.get("provider"), degraded=ev.get("degraded"),
                             **ev.get("budget", {}))
                await ws.send_json(ev)

            history.append({"role": "user", "text": user_text})
            history.append({"role": "sarathi", "text": "".join(answer_parts)})
    except WebSocketDisconnect:
        log.info("ws_disconnect", tier=tier, turns=len(history) // 2)
