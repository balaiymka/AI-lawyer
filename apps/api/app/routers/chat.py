"""Чат с AI-юристом: POST /v1/chat отдаёт поток событий (Server-Sent Events)."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.lawyer.generator import llm_provider
from app.services.lawyer.pipeline import run_chat
from app.services.lawyer.store import list_cases, load_case

router = APIRouter(tags=["chat"])


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=8000)


class ChatIn(BaseModel):
    q: str = Field(min_length=2, max_length=4000)
    role: Literal["owner", "osi", "uk", "lawyer"] | None = None
    case_id: uuid.UUID | None = None
    history: list[Turn] = Field(default_factory=list, max_length=20)


def _sse(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


HEARTBEAT_SEC = 15


@router.post("/chat")
async def chat(body: ChatIn) -> StreamingResponse:
    async def events():
        try:
            async for ev in run_chat(body.q, role=body.role, history=[t.model_dump() for t in body.history],
                                     case_id=str(body.case_id) if body.case_id else None):
                yield _sse(ev.name, ev.data)
        except Exception as e:  # поиск/БД недоступны — сообщаем клиенту, а не обрываем поток молча
            yield _sse("error", {"message": type(e).__name__})

    async def stream():
        # Пока модель думает (через Claude Code ответ приходит целиком через 60–90 с), шлём SSE-комментарий
        # «: ping» — иначе прокси и туннели (Cloudflare рвёт молчащее соединение через ~100 с) закрывают поток.
        gen = events()
        nxt = asyncio.ensure_future(gen.__anext__())
        try:
            while True:
                done, _ = await asyncio.wait({nxt}, timeout=HEARTBEAT_SEC)
                if not done:
                    yield ": ping\n\n"
                    continue
                try:
                    chunk = nxt.result()
                except StopAsyncIteration:
                    break
                yield chunk
                nxt = asyncio.ensure_future(gen.__anext__())
        finally:  # клиент ушёл — останавливаем генерацию, чтобы не жечь LLM впустую
            if not nxt.done():
                nxt.cancel()
                try:
                    await nxt
                except (asyncio.CancelledError, StopAsyncIteration, Exception):  # noqa: BLE001
                    pass
            await gen.aclose()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/chat/status")
async def chat_status() -> dict:
    provider = llm_provider()
    out: dict = {"llm": provider != "none", "provider": provider}
    if provider == "claude_code":
        from app.services.llm.claude_code import subscription_warnings

        out["warnings"] = subscription_warnings()
    return out


@router.get("/cases")
async def cases(limit: int = 30) -> list[dict]:
    return await list_cases(min(max(limit, 1), 100))


@router.get("/cases/{case_id}")
async def get_case(case_id: uuid.UUID) -> dict:
    case = await load_case(str(case_id))
    if case is None:
        raise HTTPException(404)
    return case
