"""Операции админки над базой законов. Каждая выполняется как фоновая задача (jobs.submit).

Внутри задачи — свой event loop и своё подключение к PostgreSQL (пул API привязан к другому loop).
"""

from __future__ import annotations

import asyncio
import dataclasses
from contextlib import asynccontextmanager
from datetime import date
from typing import Callable

from qdrant_client import models as qm
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.models import ActVersion, LegalAct, LegalChunk, LegalUnit
from app.db.models.cases import MessageCitation
from app.services.rag import vector_store as vs
from ingest.sources import ActSource, load_sources

Log = Callable[[str], None]


@asynccontextmanager
async def job_session():
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            yield session
    finally:
        await engine.dispose()


async def source_for(session, code: str) -> ActSource:
    """Описание акта: из sources.toml, а для добавленных через админку — из таблицы legal_acts."""
    toml = load_sources().get(code)
    if toml:
        return toml
    act = await session.scalar(select(LegalAct).where(LegalAct.code == code))
    if act is None or not act.adilet_id:
        raise ValueError(f"Акт {code} не найден")
    return ActSource(code=act.code, act_type=act.act_type, title_ru=act.title_ru, title_kk=act.title_kk,
                     adilet_id=act.adilet_id, hierarchy_level=act.hierarchy_level, number=act.number,
                     adopted_at=act.adopted_at)


async def refresh_payloads(session, code: str, log: Log) -> None:
    """Сроки действия и флаги редакций в базе поиска = как в PostgreSQL (без пересчёта векторов)."""
    act = await session.scalar(select(LegalAct).where(LegalAct.code == code))
    versions = (await session.execute(select(ActVersion).where(ActVersion.act_id == act.id))).scalars().all()
    temporal = len(versions) > 1
    client = vs.get_client()
    for v in versions:
        client.set_payload(vs.COLLECTION, payload={
            "is_current": bool(v.is_current), "temporal": temporal,
            "valid_from": v.valid_from.isoformat(), "valid_from_i": vs.date_int(v.valid_from),
            "valid_to": v.valid_to.isoformat() if v.valid_to else None, "valid_to_i": vs.date_int(v.valid_to),
        }, points=qm.Filter(must=[qm.FieldCondition(key="version_id", match=qm.MatchValue(value=str(v.id)))]))
    log(f"сроки действия обновлены в поиске: редакций {len(versions)}, история {'есть' if temporal else 'нет'}")


def _parse(src: ActSource, log: Log, use_cache: bool):
    from ingest.adilet.fetcher import fetch_act, read_cached
    from ingest.adilet.parser import merge_languages, parse_adilet_html
    from ingest.loader import source_hash

    s = get_settings()
    fetch_act(src, s.adilet_cache_dir, delay_sec=s.adilet_request_delay_sec, use_cache=use_cache)
    ru_html = read_cached(s.adilet_cache_dir, src, "ru").html
    kk_page = read_cached(s.adilet_cache_dir, src, "kk")
    ru = parse_adilet_html(ru_html, "ru")
    kk = parse_adilet_html(kk_page.html, "kk") if kk_page else None
    merged, warnings = merge_languages(ru, kk)
    log(f"разобрано: {len(merged)} единиц, казахский текст у {sum(1 for u in merged if u.text_kk or u.heading_kk)}")
    return merged, source_hash(ru_html, kk_page.html if kk_page else None)


async def check_updates(code: str, log: Log) -> dict:
    """Есть ли на Adilet редакция новее загруженной; если есть — загрузить её как действующую."""
    from ingest.adilet.versions import fetch_versions
    from ingest.indexer import index_version
    from ingest.loader import load_act

    async with job_session() as session:
        src = await source_for(session, code)
        eds = await asyncio.to_thread(fetch_versions, src.adilet_id)
        latest = next((e for e in eds if e.is_current), eds[-1])
        cur = await session.scalar(select(ActVersion).join(LegalAct, LegalAct.id == ActVersion.act_id)
                                   .where(LegalAct.code == code, ActVersion.is_current))
        log(f"на Adilet действующая редакция с {latest.revision_date}; в базе — с {cur.valid_from if cur else '—'}")
        if cur is not None and cur.valid_from >= latest.revision_date:
            return {"updated": False, "current": cur.valid_from.isoformat(), "editions_on_adilet": len(eds)}
        merged, chash = await asyncio.to_thread(_parse, src, log, False)
        res = await load_act(session, src, merged, chash, valid_from=latest.revision_date)
        log(f"{res.message}")
        if res.created:
            log(f"индексация: {await index_version(session, code, None)}")
            await refresh_payloads(session, code, log)
        return {"updated": res.created, "current": latest.revision_date.isoformat(), "editions_on_adilet": len(eds)}


async def load_edition(code: str, on: date, log: Log) -> dict:
    """Загрузить редакцию, действовавшую на дату, как историческую, и проиндексировать."""
    from ingest.adilet.versions import edition_at, fetch_versions
    from ingest.indexer import index_version
    from ingest.loader import load_historical_version

    async with job_session() as session:
        src = await source_for(session, code)
        eds = await asyncio.to_thread(fetch_versions, src.adilet_id)
        found = edition_at(eds, on)
        if found is None:
            raise ValueError(f"на {on} акт ещё не действовал")
        ed, nxt = found
        if ed.is_current:
            return {"skipped": True, "reason": "на эту дату действует текущая редакция — она уже в базе"}
        log(f"редакция с {ed.revision_date} по {nxt or 'сегодня'} (Adilet {ed.document_id})")
        merged, chash = await asyncio.to_thread(_parse, dataclasses.replace(src, adilet_id=ed.document_id), log, True)
        res = await load_historical_version(session, src, merged, chash, ed.revision_date, nxt)
        log(res.message)
        stats = await index_version(session, code, res.version_id)
        log(f"индексация: фрагментов {stats['chunks']}, векторы переиспользованы для {stats['reused_vectors']}")
        await refresh_payloads(session, code, log)
        return {"version_id": res.version_id, "valid_from": ed.revision_date.isoformat(),
                "valid_to": nxt.isoformat() if nxt else None, **stats}


async def reindex(code: str, version_id: str | None, log: Log) -> dict:
    from ingest.indexer import index_version

    async with job_session() as session:
        stats = await index_version(session, code, version_id)
        log(f"фрагментов {stats['chunks']}, новых векторов {stats['embedded']}")
        await refresh_payloads(session, code, log)
        return stats


async def delete_version(version_id: str, log: Log) -> dict:
    """Удалить историческую редакцию (действующую — нельзя). Нельзя и если на неё ссылаются сохранённые ответы."""
    import uuid as _uuid

    async with job_session() as session:
        v = await session.get(ActVersion, _uuid.UUID(version_id))
        if v is None:
            raise ValueError("редакция не найдена")
        if v.is_current:
            raise ValueError("действующую редакцию удалить нельзя — загрузите новую через «Проверить обновления»")
        act = await session.get(LegalAct, v.act_id)
        unit_ids = select(LegalUnit.id).where(LegalUnit.version_id == v.id)
        cited = await session.scalar(select(func.count()).select_from(MessageCitation)
                                     .where(MessageCitation.unit_id.in_(unit_ids)))
        if cited:
            raise ValueError(f"на эту редакцию ссылаются {cited} сохранённых ответов — удалять нельзя")
        vs.delete_version(vs.get_client(), str(v.id))
        await session.execute(delete(LegalChunk).where(LegalChunk.unit_id.in_(unit_ids)))
        # единицы удаляем снизу вверх (parent_id ссылается на ту же таблицу)
        await session.execute(LegalUnit.__table__.update().where(LegalUnit.version_id == v.id).values(parent_id=None))
        await session.execute(delete(LegalUnit).where(LegalUnit.version_id == v.id))
        await session.delete(v)
        await session.commit()
        log(f"удалена редакция {act.code} с {v.valid_from}")
        await refresh_payloads(session, act.code, log)
        return {"deleted": version_id, "act": act.code}


async def add_act(src: ActSource, log: Log) -> dict:
    """Новый акт по идентификатору Adilet: скачать, разобрать, загрузить, проиндексировать."""
    from ingest.adilet.versions import fetch_versions
    from ingest.indexer import index_version
    from ingest.loader import load_act

    async with job_session() as session:
        exists = await session.scalar(select(LegalAct).where(LegalAct.code == src.code))
        if exists is not None:
            raise ValueError(f"код {src.code} уже занят")
        try:
            eds = await asyncio.to_thread(fetch_versions, src.adilet_id)
            valid_from = next((e for e in eds if e.is_current), eds[-1]).revision_date
            log(f"на Adilet редакций: {len(eds)}, действующая с {valid_from}")
        except Exception as e:  # noqa: BLE001 — хронология необязательна
            valid_from = date.today()
            log(f"хронологию получить не удалось ({type(e).__name__}) — дата редакции = сегодня")
        merged, chash = await asyncio.to_thread(_parse, src, log, False)
        if len(merged) < 3:
            raise ValueError("текст не разобрался — проверьте идентификатор Adilet")
        res = await load_act(session, src, merged, chash, valid_from=valid_from)
        log(res.message)
        stats = await index_version(session, src.code, None)
        log(f"индексация: фрагментов {stats['chunks']}")
        await refresh_payloads(session, src.code, log)
        return {"act": src.code, **stats}


def retrieval_eval(log: Log) -> dict:
    """Контрольный набор вопросов (tests/eval/retrieval_gold.jsonl) через поиск без LLM. Синхронно: поиск синхронный."""
    from tests.eval import run_retrieval_eval as ev

    items = ev.load_gold()
    log(f"вопросов в наборе: {len(items)}")
    summary, rows = ev.run_heuristic(items, log=lambda m: None)
    path = ev.write_report(summary, rows)
    misses = [r for r in rows if not r["rank"] or r["rank"] > 10]
    log(f"R@1 {summary['recall@1']:.0%} · R@5 {summary['recall@5']:.0%} · R@10 {summary['recall@10']:.0%} · "
        f"MRR {summary['mrr']:.2f} · {summary['sec_per_query']:.1f} с/вопрос")
    for m in misses[:10]:
        log(f"промах {m['id']}: {m['q'][:60]}")
    log(f"отчёт: {path.name}")
    return {k: summary[k] for k in ("n", "recall@1", "recall@5", "recall@10", "mrr")}


def latest_eval() -> dict | None:
    import json

    from tests.eval import run_retrieval_eval as ev

    reports = sorted((ev.HERE / "reports").glob("*-heuristic.json"))
    if not reports:
        return None
    data = json.loads(reports[-1].read_text(encoding="utf-8"))
    s = data["summary"]
    stamp = reports[-1].name[:13]  # 20261116-2015
    misses = [{k: r.get(k) for k in ("id", "q", "gold", "top")} for r in data["rows"] if not r["rank"] or r["rank"] > 10]
    return {"at": f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[9:11]}:{stamp[11:13]}", "n": s["n"],
            "recall@1": s["recall@1"], "recall@5": s["recall@5"], "recall@10": s["recall@10"], "mrr": s["mrr"],
            "sec_per_query": s["sec_per_query"], "by_act": s.get("by_act", {}), "misses": misses}
