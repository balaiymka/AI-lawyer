"""Проверка состояния сервиса: БД, Qdrant, база законов, модели, LLM.

Отвечает всегда, даже если часть сервисов лежит: так по одному запросу видно,
что именно сломалось. Код 503 — когда не работает БД или Qdrant (без них поиск невозможен).
"""

import asyncio
import time

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.services.rag import models as rag_models
from app.services.rag import vector_store

router = APIRouter(tags=["health"])


def _err(exc: Exception) -> str:
    return f"error: {type(exc).__name__}"


async def check_db(session: AsyncSession) -> dict:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — health должен отвечать, даже если БД лежит
        return {"status": _err(exc)}
    return {"status": "ok"}


async def check_laws(session: AsyncSession) -> dict:
    """Сколько актов и редакций загружено и когда последний раз сверялись с Adilet."""
    try:
        row = (await session.execute(text(
            "SELECT (SELECT count(*) FROM legal_acts),"
            "       (SELECT count(*) FROM act_versions),"
            "       (SELECT count(*) FROM act_versions WHERE is_current),"
            "       (SELECT max(fetched_at) FROM act_versions)"
        ))).one()
    except Exception as exc:  # noqa: BLE001
        return {"status": _err(exc)}
    acts, versions, current, last = row
    return {
        "status": "ok" if acts and current == acts else "warning",
        "acts": acts,
        "versions": versions,
        "current_versions": current,
        "last_fetched_at": last.isoformat() if last else None,
    }


def check_qdrant() -> dict:
    try:
        client = vector_store.get_client()
        if not client.collection_exists(vector_store.COLLECTION):
            return {"status": "error: no collection"}
        points = client.count(vector_store.COLLECTION, exact=False).count
    except Exception as exc:  # noqa: BLE001
        return {"status": _err(exc)}
    return {"status": "ok" if points else "warning", "points": points}


def check_models() -> dict:
    """Только показывает, загружены ли модели в память. Сам health их не грузит — это ~4 ГБ."""
    s = get_settings()
    return {
        "embedder": {"name": s.embed_model, "loaded": rag_models.get_embedder.cache_info().currsize > 0},
        "reranker": {"name": s.rerank_model, "loaded": rag_models.get_reranker.cache_info().currsize > 0},
    }


def check_llm() -> dict:
    s = get_settings()
    if s.llm_provider == "claude_code":
        from app.services.llm.claude_code import find_claude
        ready = find_claude() is not None
        return {"provider": "claude_code", "model": s.claude_model or "default", "ready": ready}
    # Ключ не показываем — только факт, что он задан.
    return {"provider": s.llm_provider, "model": s.llm_model, "ready": bool(s.anthropic_api_key)}


@router.get("/health")
async def health(response: Response, session: AsyncSession = Depends(get_session)) -> dict:
    started = time.perf_counter()
    db = await check_db(session)
    laws = await check_laws(session) if db["status"] == "ok" else {"status": "skipped"}
    qdrant = await asyncio.to_thread(check_qdrant)
    llm = check_llm()

    critical_ok = db["status"] == "ok" and qdrant["status"] in ("ok", "warning")
    if not critical_ok:
        status = "down"
        response.status_code = 503
    elif qdrant["status"] != "ok" or laws["status"] != "ok" or not llm["ready"]:
        status = "degraded"
    else:
        status = "ok"
    return {
        "status": status,
        "db": db["status"],  # старое поле — оставлено для совместимости
        "qdrant": qdrant,
        "laws": laws,
        "models": check_models(),
        "llm": llm,
        "took_ms": round((time.perf_counter() - started) * 1000),
    }
