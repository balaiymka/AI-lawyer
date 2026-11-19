"""Конвейер чата: нормализация → поиск норм → ответ юриста → проверка ссылок → сохранение.

Отдаёт события для SSE: status, normalized, sources, delta, answer, error, done.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi.concurrency import run_in_threadpool

from app.services.lawyer.context import ContextChunk, build_context
from app.services.lawyer.generator import (Delta, Final, LawyerError, build_user_content, generate_demo,
                                           generate_answer, llm_available)
from app.services.lawyer.verify import verify_answer
from app.services.nlu.normalizer import normalize, to_search_request
from app.services.rag.retriever import search

log = logging.getLogger(__name__)
CONTEXT_TOP_K = 8


@dataclass
class Event:
    name: str
    data: dict


async def run_chat(text: str, role: str | None = None, history: list[dict] | None = None,
                   case_id: str | None = None, persist: bool = True) -> AsyncIterator[Event]:
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    yield Event("status", {"stage": "normalize"})
    nq = await normalize(text)
    timings["normalize"] = (time.perf_counter() - t0) * 1000
    yield Event("normalized", {"reply_lang": nq.reply_lang, "category": nq.category, "source": nq.source,
                               "normalized_ru": nq.normalized_ru, "event_date": nq.event_date,
                               "event_date_precision": nq.event_date_precision})

    t0 = time.perf_counter()
    yield Event("status", {"stage": "search"})
    req = to_search_request(text, nq, top_k=CONTEXT_TOP_K)
    edition, editions = None, []
    if req.as_of is not None:
        try:
            from app.services.lawyer.editions import resolve_editions

            editions = await resolve_editions(req.as_of)
            req.act_dates = {e.act_code: e.search_date for e in editions}
            edition = next((e for e in editions if e.act_code == "ZHO"), editions[0] if editions else None)
        except Exception:  # без БД — ищем по дате как есть
            log.exception("edition resolution failed")
    results, trace = await run_in_threadpool(search, req)
    timings["search"] = (time.perf_counter() - t0) * 1000
    context_xml, chunks = build_context(results, nq.reply_lang)
    yield Event("sources", {"sources": [c.public() for c in chunks]})

    t0 = time.perf_counter()
    yield Event("status", {"stage": "answer"})
    use_llm = llm_available()
    if use_llm:
        normalized = nq.model_dump()
        if editions:
            normalized["editions"] = [e.public() for e in editions]
        gen = generate_answer(build_user_content(context_xml, normalized, text, role, history))
    else:
        gen = generate_demo(chunks, nq.reply_lang)

    final: Final | None = None
    try:
        async for item in gen:
            if isinstance(item, Delta):
                yield Event("delta", {"text": item.text})
            else:
                final = item
    except LawyerError as e:  # отказ модели / обрезанный ответ
        log.warning("lawyer generation failed: %s", e)
    except Exception:  # сеть, ключ, лимиты — не роняем чат
        log.exception("lawyer generation error")
    if final is None and use_llm:
        yield Event("notice", {"code": "llm_failed"})
        async for item in generate_demo(chunks, nq.reply_lang):
            if isinstance(item, Final):
                final = item
    assert final is not None
    timings["answer"] = (time.perf_counter() - t0) * 1000

    answer, verification = verify_answer(final.answer, chunks)
    yield Event("answer", {"answer": answer.model_dump(), "verification": verification.dict(),
                           "mode": final.mode, "reply_lang": nq.reply_lang, "timings_ms": timings,
                           "event_date": nq.event_date, "event_date_precision": nq.event_date_precision,
                           "edition": edition.public() if edition else None,
                           "editions": [e.public() for e in editions]})

    saved_case = case_id
    if persist:
        try:
            from app.services.lawyer.store import save_exchange

            saved_case = await save_exchange(
                case_id=case_id, text=text, normalized=nq.model_dump(), answer=answer.model_dump(),
                reply_lang=nq.reply_lang, chunks=chunks, cited={b.chunk_id for b in answer.legal_basis},
                model=final.model, usage=final.usage, needs_review=verification.needs_review,
                queries=[q.q for q in nq.search_queries], candidates=trace.candidates,
                latency_ms={**trace.timings_ms, **timings},
                meta={"mode": final.mode, "verification": verification.dict(),
                      "sources": [c.public() for c in chunks]})
        except Exception:
            log.exception("failed to save chat exchange")
    yield Event("done", {"case_id": saved_case})


def new_id() -> str:
    return str(uuid.uuid4())


__all__ = ["Event", "run_chat", "ContextChunk"]
