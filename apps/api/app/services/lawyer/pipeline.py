"""Конвейер чата: нормализация (+ подвопросы) → поиск норм по каждому подвопросу (+ граф закона) →
разбор веток → ответ юриста → фактчек и переработка → проверка ссылок → сохранение.

Отдаёт события для SSE: status (normalize | search | answer | factcheck), normalized, sources, delta, answer,
notice, done.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace

from fastapi.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.services.lawyer.analysis import (BranchAnalysis, FactIssue, analyze_branch, branches_block, fact_check,
                                          review_block)
from app.services.lawyer.context import ContextChunk, build_context
from app.services.lawyer.generator import (Delta, Final, LawyerError, build_user_content, generate_demo,
                                           generate_answer, llm_available)
from app.services.lawyer.verify import scope_mismatches, unverified_refs, verify_answer
from app.services.nlu.normalizer import SubQuestion, normalize, to_search_request
from app.services.rag.graph import expand_with_graph
from app.services.rag.refs import extract_refs
from app.services.rag.retriever import Result, SearchRequest, SearchTrace, search

log = logging.getLogger(__name__)
ARTICLE_NUM = re.compile(r"(?<![а-яё])(?:ст\.?|статья|статьи|статье|п\.|пункт\w*)\s*\d+(?:-\d+)?", re.I)
CONTEXT_TOP_K = 8


@dataclass
class Event:
    name: str
    data: dict


async def _search(req: SearchRequest) -> tuple[list[Result], SearchTrace]:
    """Гибридный поиск + связанные по графу закона пункты (исключения, перечни)."""
    results, trace = await run_in_threadpool(search, req)
    limit = get_settings().graph_limit
    if limit and results:
        t0 = time.perf_counter()
        results = results + await expand_with_graph(results, req.reply_lang, limit)
        trace.timings_ms["graph"] = (time.perf_counter() - t0) * 1000
    return results, trace


def _merge(lists: list[list[Result]]) -> list[Result]:
    """Результаты веток по очереди (1-й первой ветки, 1-й второй…), без повторов: каждая ветка видна в контексте."""
    out: list[Result] = []
    seen: set[str] = set()
    for i in range(max((len(x) for x in lists), default=0)):
        for lst in lists:
            if i < len(lst) and lst[i].unit_id not in seen:
                seen.add(lst[i].unit_id)
                out.append(lst[i])
    return out


def _branch_request(base: SearchRequest, sq: SubQuestion, top_k: int) -> SearchRequest:
    refs = list(base.refs)
    for r in extract_refs(sq.question):
        if r not in refs:
            refs.append(r)
    queries = [q for q in [sq.question, *sq.search_queries] if q.strip()][:4]
    if not base.refs:
        # Пользователь статей не называл, а модель могла дописать номер «по памяти» («ст 42-1») —
        # такой номер уводит лексический поиск в чужую статью. Ищем по смыслу.
        queries = [ARTICLE_NUM.sub(" ", q).strip() for q in queries]
        refs = []
    return replace(base, queries=[q for q in queries if q], rerank_query=sq.question, refs=refs, top_k=top_k)


async def _analyze_branches(subs: list[SubQuestion], branch_results: list[list[Result]], req: SearchRequest,
                            lang: str, text: str, rounds: int) -> list[BranchAnalysis | None]:
    """Разбор каждой ветки; если ветке не хватает норм — дополнительный поиск и повторный разбор.

    branch_results дополняется на месте: у каждой ветки остаётся свой набор источников."""

    async def one(i: int, sq: SubQuestion) -> BranchAnalysis | None:
        b = None
        for rnd in range(rounds + 1):
            try:
                b = await analyze_branch(sq.question, sq.kind, build_context(branch_results[i], lang)[0], text)
            except Exception as e:  # noqa: BLE001
                log.warning("branch analysis failed (%s): %s", sq.question[:60], e)
                return b
            b.rounds = rnd + 1
            b.sources = [r.path for r in branch_results[i]]
            if rnd == rounds or not b.follow_up_queries:
                return b
            fq = b.follow_up_queries[:3]
            extra, _ = await _search(replace(_branch_request(req, sq, 4), queries=fq, rerank_query=fq[0]))
            have = {r.unit_id for r in branch_results[i]}
            new = [r for r in extra if r.unit_id not in have]
            if not new:
                return b
            branch_results[i] = branch_results[i] + new
        return b

    return list(await asyncio.gather(*[one(i, sq) for i, sq in enumerate(subs)]))


async def _collect(gen) -> Final | None:
    final = None
    async for item in gen:
        if isinstance(item, Final):
            final = item
    return final


async def run_chat(text: str, role: str | None = None, history: list[dict] | None = None,
                   case_id: str | None = None, persist: bool = True) -> AsyncIterator[Event]:
    settings = get_settings()
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    yield Event("status", {"stage": "normalize"})
    nq = await normalize(text)
    timings["normalize"] = (time.perf_counter() - t0) * 1000
    use_llm = llm_available()
    # Один подвопрос — одна ветка: поиск общий, но разбор с дозапросом норм (итеративный поиск) тот же.
    subs = nq.sub_questions[: settings.max_sub_questions] if settings.decompose_enabled and use_llm else []
    yield Event("normalized", {"reply_lang": nq.reply_lang, "category": nq.category, "source": nq.source,
                               "normalized_ru": nq.normalized_ru, "event_date": nq.event_date,
                               "event_date_precision": nq.event_date_precision,
                               "sub_questions": [q.model_dump() for q in subs if len(subs) > 1]})

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
    branch_results: list[list[Result]] = []
    if len(subs) > 1:
        # Каждый подвопрос ищется отдельно: иначе реранкер отдаёт все места одной теме (голосованию),
        # а нормы про взносы или общее имущество в контекст не попадают.
        trace = SearchTrace()
        for sq in subs:
            res, tr = await _search(_branch_request(req, sq, settings.branch_top_k))
            branch_results.append(res)
            trace.candidates += tr.candidates
            for k, v in tr.timings_ms.items():
                trace.timings_ms[k] = trace.timings_ms.get(k, 0.0) + v
        results = _merge(branch_results)
    else:
        results, trace = await _search(req)
        if subs:
            branch_results = [list(results)]
    timings["search"] = (time.perf_counter() - t0) * 1000
    context_xml, chunks = build_context(results, nq.reply_lang)
    yield Event("sources", {"sources": [c.public() for c in chunks]})

    t0 = time.perf_counter()
    yield Event("status", {"stage": "answer"})
    normalized = nq.model_dump()
    if editions:
        normalized["editions"] = [e.public() for e in editions]
    blocks: list[str] = []
    branches = []
    if subs:
        tb = time.perf_counter()
        got = await _analyze_branches(subs, branch_results, req, nq.reply_lang, text, settings.branch_followup_rounds)
        branches = [b for b in got if b is not None]
        # Ветки могли дозапросить нормы — общий контекст собираем заново, сохраняя порядок веток.
        merged = _merge(branch_results)
        if len(merged) != len(results):
            results = merged
            context_xml, chunks = build_context(results, nq.reply_lang)
            yield Event("sources", {"sources": [c.public() for c in chunks]})
        if branches:
            blocks.append(branches_block(branches))
        timings["branches"] = (time.perf_counter() - tb) * 1000

    if use_llm:
        gen = generate_answer(build_user_content(context_xml, normalized, text, role, history, blocks))
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

    # Фактчек: второй юрист сверяет цифры, пороги и исключения с нормами; при ошибках ответ переписывается.
    fc_info: dict | None = None
    if final.mode == "llm" and settings.factcheck_enabled:
        t0 = time.perf_counter()
        yield Event("status", {"stage": "factcheck"})
        # Проверка → (дополнительный поиск, если не хватает нормы) → исправление → повторная проверка.
        # Не больше factcheck_rounds исправлений, чтобы не зациклиться.
        fc_info = {"verdict": "ok", "issues": [], "extra_queries": [], "revised": False, "rounds": []}
        try:
            for rnd in range(settings.factcheck_rounds + 1):
                fc = await fact_check(context_xml, text, final.answer.model_dump_json())
                # Детерминированная проверка поверх мнения модели: номер статьи без нормы в контексте — ошибка.
                for art in unverified_refs(final.answer, chunks):
                    fc.issues.append(FactIssue(
                        claim=f"ссылка на статью {art}",
                        problem="статьи с таким номером нет среди найденных норм (<context>) — номер не подтверждён текстом",
                        correction="убери номер или сошлись на норму из <context>; если нужной нормы нет — прямо скажи, "
                                   "что в базе портала она не найдена"))
                    fc.verdict = "fix"
                # Сфера действия: норма особого режима (ЖСК, госжилфонд, служебное жильё) без признаков его в вопросе.
                for ref, regime in scope_mismatches(final.answer, chunks, text):
                    fc.issues.append(FactIssue(
                        claim=f"применена {ref}",
                        problem=f"норма относится к особому режиму «{regime}» (см. заголовок главы/статьи), а в вопросе "
                                "пользователя таких признаков нет",
                        correction="опирайся на нормы, которые относятся к ситуации пользователя; норму особого режима "
                                   "упоминай только с оговоркой, если ситуация может под него подпадать"))
                    fc.verdict = "fix"
                fc_info["rounds"].append({"verdict": fc.verdict, "issues": len(fc.issues)})
                fc_info.update(verdict=fc.verdict, issues=[i.model_dump() for i in fc.issues],
                               extra_queries=fc.extra_queries)
                if fc.verdict != "fix" or rnd == settings.factcheck_rounds:
                    break
                if fc.extra_queries:
                    extra_req = replace(req, queries=fc.extra_queries[:3], rerank_query=fc.extra_queries[0],
                                        refs=[], top_k=4)
                    extra, _ = await _search(extra_req)
                    have = {r.unit_id for r in results}
                    new = [r for r in extra if r.unit_id not in have]
                    if new:
                        results = results + new
                        context_xml, chunks = build_context(results, nq.reply_lang)
                        yield Event("sources", {"sources": [c.public() for c in chunks]})
                revised = await _collect(generate_answer(build_user_content(
                    context_xml, normalized, text, role, history, blocks + [review_block(fc)])))
                if revised is None:
                    break
                final = revised
                fc_info["revised"] = True
        except Exception:  # noqa: BLE001 — фактчек улучшает ответ, но не должен его ронять
            log.exception("fact check failed")
            fc_info = {**fc_info, "verdict": "error"}
        timings["factcheck"] = (time.perf_counter() - t0) * 1000

    answer, verification = verify_answer(final.answer, chunks, text)
    analysis = {"sub_questions": [q.model_dump() for q in subs], "branches": [b.model_dump() for b in branches],
                "fact_check": fc_info}
    yield Event("answer", {"answer": answer.model_dump(), "verification": verification.dict(),
                           "mode": final.mode, "reply_lang": nq.reply_lang, "timings_ms": timings,
                           "event_date": nq.event_date, "event_date_precision": nq.event_date_precision,
                           "edition": edition.public() if edition else None,
                           "editions": [e.public() for e in editions], "analysis": analysis})

    saved_case = case_id
    if persist:
        try:
            from app.services.lawyer.store import save_exchange

            cited = {b.chunk_id for b in answer.legal_basis} | {c for x in answer.calculations for c in x.citations}
            saved_case = await save_exchange(
                case_id=case_id, text=text, normalized=nq.model_dump(), answer=answer.model_dump(),
                reply_lang=nq.reply_lang, chunks=chunks, cited=cited,
                model=final.model, usage=final.usage, needs_review=verification.needs_review,
                queries=[q.q for q in nq.search_queries] + [q.question for q in subs], candidates=trace.candidates,
                latency_ms={**trace.timings_ms, **timings},
                meta={"mode": final.mode, "verification": verification.dict(),
                      "sources": [c.public() for c in chunks], "analysis": analysis})
        except Exception:
            log.exception("failed to save chat exchange")
    yield Event("done", {"case_id": saved_case})


def new_id() -> str:
    return str(uuid.uuid4())


__all__ = ["Event", "run_chat", "ContextChunk"]
