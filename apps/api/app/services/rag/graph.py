"""Граф закона в PostgreSQL (legal_refs): построение при загрузке и подтягивание связанных пунктов при поиске.

Подтягиваем в обе стороны:
  * найден п. 8 ст. 42 («за исключением подпунктов 6)–16) пункта 5») → добавляем п. 5 (перечень вопросов);
  * найден пп. 7) п. 5 («утверждение размера текущих взносов») → добавляем п. 8, который для этого
    подпункта задаёт другое большинство (входящее ребро-исключение).
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LegalRef, LegalUnit
from app.services.rag.law_graph import extract_graph_refs

log = logging.getLogger(__name__)

# Если пункт ссылается больше чем на COLLAPSE подпунктов одного пункта — подтягиваем пункт целиком (перечень).
COLLAPSE = 2


async def build_graph(session: AsyncSession, version_id: uuid.UUID) -> int:
    """Пересобрать рёбра одной редакции. Возвращает число рёбер."""
    rows = (await session.execute(
        select(LegalUnit.id, LegalUnit.path, LegalUnit.text_ru, LegalUnit.parent_id)
        .where(LegalUnit.version_id == version_id, LegalUnit.is_repealed.is_(False)))).all()
    by_path = {r.path: r.id for r in rows}
    has_children = {r.parent_id for r in rows if r.parent_id}
    edges: dict[tuple, str] = {}
    for r in rows:
        if not r.text_ru or r.id in has_children and r.path.count("/") == 0:
            continue  # статья целиком повторяет текст своих пунктов — разбираем пункты
        for ref in extract_graph_refs(r.text_ru, r.path):
            target = by_path.get(ref.target)
            if target is None and "/sp" in ref.target:  # подпункт не выделен парсером — берём пункт
                target = by_path.get(ref.target.rsplit("/", 1)[0])
            if target is None or target == r.id:
                continue
            key = (r.id, target)
            if edges.get(key) != "exception":
                edges[key] = ref.kind
    await session.execute(delete(LegalRef).where(LegalRef.version_id == version_id))
    if edges:
        session.add_all(LegalRef(version_id=version_id, from_unit_id=f, to_unit_id=t, kind=k)
                        for (f, t), k in edges.items())
    await session.commit()
    return len(edges)


async def build_all(session: AsyncSession, act_code: str | None = None) -> dict[str, int]:
    sql = ("SELECT v.id, a.code, v.is_current, v.valid_from FROM act_versions v JOIN legal_acts a ON a.id = v.act_id"
           + (" WHERE a.code = :code" if act_code else "") + " ORDER BY a.code, v.valid_from")
    out: dict[str, int] = {}
    for vid, code, current, valid_from in (await session.execute(text(sql), {"code": act_code})).all():
        n = await build_graph(session, vid)
        out[f"{code} {valid_from or ''}{' (действующая)' if current else ''}"] = n
    return out


@dataclass
class Link:
    unit_id: str  # какой пункт добавить
    source_unit: str  # из-за какого найденного пункта
    source_path: str
    relation: str  # exception | reference | exception_for | rule_for_list | referenced_by


async def find_links(session: AsyncSession, unit_ids: list[str], limit: int = 5) -> list[Link]:
    """Связанные пункты для найденных: исключения — первыми."""
    if not unit_ids:
        return []
    ids = [uuid.UUID(u) for u in unit_ids]
    # исходящие рёбра найденных пунктов
    out_rows = (await session.execute(text("""
        SELECT r.from_unit_id, fu.path, r.to_unit_id, tu.parent_id, r.kind
        FROM legal_refs r JOIN legal_units fu ON fu.id = r.from_unit_id JOIN legal_units tu ON tu.id = r.to_unit_id
        WHERE r.from_unit_id = ANY(:ids)"""), {"ids": ids})).all()
    # входящие: кто ссылается на найденный пункт, на его подпункты или (исключением) на соседние подпункты
    # того же перечня — такая норма задаёт правило для всего перечня («… за исключением подпунктов 6)–16)»
    # значит, что подпункт 3) решается по общему правилу этой же нормы).
    in_rows = (await session.execute(text("""
        WITH found AS (SELECT id, parent_id FROM legal_units WHERE id = ANY(:ids))
        SELECT r.from_unit_id, r.to_unit_id, tu.parent_id, r.kind, tu.path,
               (SELECT f.id FROM found f WHERE f.parent_id = tu.parent_id LIMIT 1) AS sibling
        FROM legal_refs r JOIN legal_units tu ON tu.id = r.to_unit_id
        WHERE r.to_unit_id = ANY(:ids) OR tu.parent_id = ANY(:ids)
           OR (r.kind = 'exception' AND tu.parent_id IN (SELECT parent_id FROM found WHERE parent_id IS NOT NULL))
        """), {"ids": ids})).all()

    have = set(ids)
    rank = {u: i for i, u in enumerate(ids)}
    cands: list[tuple[float, int, Link]] = []  # (приоритет, ранг источника, ссылка)

    groups: dict[tuple, list] = defaultdict(list)
    for src, src_path, to, parent, kind in out_rows:
        groups[(src, parent)].append((to, kind, src_path))
    for (src, parent), items in groups.items():
        kind = "exception" if any(k == "exception" for _, k, _ in items) else "reference"
        targets = [parent] if parent and len(items) > COLLAPSE else [t for t, _, _ in items]
        for t in targets:
            if t in have or (parent in have and t != parent):
                continue
            cands.append((0 if kind == "exception" else 2, rank[src], Link(str(t), str(src), items[0][2], kind)))

    for src, to, parent, kind, to_path, sibling in in_rows:
        if src in have:
            continue
        if to in have or parent in have:
            found = to if to in have else parent
            relation = "exception_for" if kind == "exception" else "referenced_by"
        else:
            found, relation = sibling, "rule_for_list"
        prio = {"exception_for": 1.0, "rule_for_list": 1.5}.get(relation, 3.0)
        cands.append((prio, rank.get(found, 99), Link(str(src), str(found), to_path, relation)))

    links: list[Link] = []
    seen: set[str] = set()
    for _, _, link in sorted(cands, key=lambda c: (c[0], c[1])):
        if link.unit_id in seen:
            continue
        seen.add(link.unit_id)
        links.append(link)
        if len(links) >= limit:
            break
    return links


def fetch_link_results(links: list[Link], reply_lang: str):
    """Пункты из Qdrant (нужны chunk_id для цитат) в виде Result поиска."""
    from qdrant_client import models

    from app.services.rag import vector_store as vs
    from app.services.rag.retriever import _unit_result

    if not links:
        return []
    client = vs.get_client()
    pts, _ = client.scroll(vs.COLLECTION, scroll_filter=models.Filter(must=[models.FieldCondition(
        key="unit_id", match=models.MatchAny(any=[l.unit_id for l in links]))]), limit=len(links) * 4, with_payload=True)
    by_unit: dict[str, list] = defaultdict(list)
    for p in pts:
        by_unit[(p.payload or {})["unit_id"]].append(p)
    out = []
    for l in links:
        if l.unit_id not in by_unit:
            continue
        r = _unit_result(by_unit[l.unit_id], l.unit_id, reply_lang, l.source_path)
        r.meta["relation"] = l.relation
        r.channels = {"graph": 1}
        out.append(r)
    return out


async def expand_with_graph(results: list, reply_lang: str, limit: int = 5, seeds: int = 8) -> list:
    """Связанные по графу пункты для первых `seeds` результатов. Без БД — пустой список (поиск работает как раньше)."""
    from fastapi.concurrency import run_in_threadpool

    from app.db.session import SessionLocal

    try:
        async with SessionLocal() as session:
            links = await find_links(session, [r.unit_id for r in results[:seeds]], limit)
        present = {r.unit_id for r in results}
        links = [l for l in links if l.unit_id not in present]
        return await run_in_threadpool(fetch_link_results, links, reply_lang)
    except Exception:  # noqa: BLE001 — граф — улучшение, не должен ронять чат
        log.exception("graph expansion failed")
        return []
