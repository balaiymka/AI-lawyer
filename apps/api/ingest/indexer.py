"""Индексация редакции акта: legal_units → legal_chunks (PostgreSQL) → векторы (Qdrant).

У каждого фрагмента в Qdrant — срок действия его редакции (`valid_from_i`/`valid_to_i`, ГГГГММДД) и признак
`temporal` (у акта загружена история). Так поиск может взять редакцию, действовавшую на дату события.
Векторы текста, который не менялся между редакциями, берутся из уже посчитанных (по `content_sha`).
"""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone

from qdrant_client import models
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActVersion, Lang, LegalAct, LegalChunk, LegalUnit
from app.services.rag import vector_store as vs
from app.services.rag.chunker import ActInfo, UnitRow, build_chunks
from app.services.rag.models import get_embedder


def content_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


async def index_act(session: AsyncSession, act_code: str, batch_size: int = 8) -> dict:
    """Действующая редакция (как раньше)."""
    return await index_version(session, act_code, None, batch_size)


async def index_version(session: AsyncSession, act_code: str, version_id: uuid.UUID | str | None,
                        batch_size: int = 8) -> dict:
    q = select(LegalAct, ActVersion).join(ActVersion, ActVersion.act_id == LegalAct.id).where(LegalAct.code == act_code)
    q = q.where(ActVersion.id == uuid.UUID(str(version_id))) if version_id else q.where(ActVersion.is_current)
    act, version = (await session.execute(q)).one()
    n_versions = await session.scalar(select(func.count()).select_from(ActVersion).where(ActVersion.act_id == act.id))
    temporal = (n_versions or 0) > 1

    rows = (await session.execute(select(LegalUnit).where(LegalUnit.version_id == version.id))).scalars().all()
    units = [
        UnitRow(id=u.id, parent_id=u.parent_id, unit_type=u.unit_type, number=u.number, path=u.path,
                heading_ru=u.heading_ru, heading_kk=u.heading_kk, text_ru=u.text_ru, text_kk=u.text_kk,
                is_repealed=u.is_repealed, ord=u.ord)
        for u in rows
    ]
    drafts = build_chunks(units, ActInfo(act.code, act.title_ru, act.title_kk))

    # Фрагменты обновляются на месте: на них могут ссылаться цитаты из сохранённых чатов (message_citations).
    existing = {
        (c.unit_id, c.lang.value): c
        for c in (await session.execute(
            select(LegalChunk).where(LegalChunk.unit_id.in_([u.id for u in units])))).scalars().all()
    }
    chunk_rows = []
    for d in drafts:
        row = existing.pop((d.unit_id, d.lang), None)
        if row is None:
            row = LegalChunk(unit_id=d.unit_id, lang=Lang(d.lang))
            session.add(row)
        row.breadcrumb, row.content, row.token_count = d.breadcrumb, d.content, len(d.content) // 4
        chunk_rows.append(row)
    stale = [c.id for c in existing.values()]
    if stale:  # больше не нужны; удаляем только те, на которые никто не ссылается
        from app.db.models.cases import MessageCitation

        cited = set((await session.execute(
            select(MessageCitation.chunk_id).where(MessageCitation.chunk_id.in_(stale)))).scalars().all())
        if [i for i in stale if i not in cited]:
            await session.execute(delete(LegalChunk).where(LegalChunk.id.in_([i for i in stale if i not in cited])))
    await session.flush()

    client = vs.get_client()
    vs.ensure_collection(client)
    shas = [content_sha(d.content) for d in drafts]
    cached = vs.lookup_vectors(client, sorted(set(shas)))
    todo = [i for i, sh in enumerate(shas) if sh not in cached]
    t0 = time.perf_counter()
    fresh = get_embedder().encode([drafts[i].content for i in todo], max_length=1024, batch_size=batch_size) if todo else []
    embed_sec = time.perf_counter() - t0
    vectors: dict[int, tuple] = {}
    for i, enc in zip(todo, fresh):
        vectors[i] = (enc.dense, models.SparseVector(indices=list(enc.sparse), values=list(enc.sparse.values())))
    for i, sh in enumerate(shas):
        if i not in vectors:
            vectors[i] = cached[sh]

    vs.delete_version(client, str(version.id))
    points = [
        models.PointStruct(
            id=str(row.id),
            vector={vs.DENSE: vectors[i][0], vs.SPARSE: vectors[i][1]},
            payload={
                "chunk_id": str(row.id), "unit_id": str(d.unit_id), "act_code": d.act_code, "lang": d.lang,
                "path": d.path, "article": d.article, "point": d.point, "kind": d.kind,
                "breadcrumb": d.breadcrumb, "content": d.content, "content_sha": shas[i],
                "version_id": str(version.id), "valid_from": version.valid_from.isoformat(),
                "valid_to": version.valid_to.isoformat() if version.valid_to else None,
                "valid_from_i": vs.date_int(version.valid_from), "valid_to_i": vs.date_int(version.valid_to),
                "is_current": bool(version.is_current), "temporal": temporal,
            },
        )
        for i, (row, d) in enumerate(zip(chunk_rows, drafts))
    ]
    vs.upsert(client, points)

    now = datetime.now(timezone.utc)
    for row in chunk_rows:
        row.embedded_at = now
    await session.commit()
    return {"act": act.code, "version": str(version.id), "valid_from": version.valid_from.isoformat(),
            "valid_to": version.valid_to.isoformat() if version.valid_to else None, "chunks": len(drafts),
            "reused_vectors": len(drafts) - len(todo), "embedded": len(todo), "embed_sec": round(embed_sec, 1),
            "temporal": temporal}
