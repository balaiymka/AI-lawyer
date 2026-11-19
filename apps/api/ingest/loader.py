"""Запись разобранного акта в PostgreSQL как новой редакции (если текст изменился)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActVersion, LegalAct, LegalUnit
from ingest.adilet.parser import MergedUnit
from ingest.sources import ActSource


@dataclass
class LoadResult:
    act_code: str
    version_id: str | None
    created: bool
    units: int
    message: str


def source_hash(ru_html: str, kk_html: str | None) -> str:
    h = hashlib.sha256(ru_html.encode("utf-8"))
    if kk_html:
        h.update(b"\x00")
        h.update(kk_html.encode("utf-8"))
    return h.hexdigest()


async def _upsert_act(session: AsyncSession, src: ActSource) -> LegalAct:
    act = (await session.execute(select(LegalAct).where(LegalAct.code == src.code))).scalar_one_or_none()
    if act is None:
        act = LegalAct(code=src.code)
        session.add(act)
    act.act_type = src.act_type
    act.title_ru = src.title_ru
    act.title_kk = src.title_kk
    act.number = src.number
    act.adopted_at = src.adopted_at
    act.adilet_id = src.adilet_id
    act.adilet_url_ru = src.url("ru")
    act.adilet_url_kk = src.url("kk")
    act.hierarchy_level = src.hierarchy_level
    await session.flush()
    return act


async def load_act(
    session: AsyncSession,
    src: ActSource,
    units: list[MergedUnit],
    content_hash: str,
    valid_from: date | None = None,
) -> LoadResult:
    act = await _upsert_act(session, src)

    current = (
        await session.execute(select(ActVersion).where(ActVersion.act_id == act.id, ActVersion.is_current))
    ).scalar_one_or_none()
    if current is not None and current.source_hash == content_hash:
        await session.commit()
        return LoadResult(src.code, str(current.id), False, 0, "текст не изменился — новая редакция не создана")

    today = valid_from or date.today()
    if current is not None:
        await session.execute(
            update(ActVersion).where(ActVersion.id == current.id).values(is_current=False, valid_to=today)
        )
        await session.flush()

    version = ActVersion(act_id=act.id, valid_from=today, source_hash=content_hash, is_current=True)
    session.add(version)
    await session.flush()

    ids: dict[str, object] = {}
    for u in units:  # родители всегда идут раньше потомков (порядок обхода дерева)
        row = LegalUnit(
            version_id=version.id,
            parent_id=ids.get(u.parent_path) if u.parent_path else None,
            unit_type=u.unit_type,
            number=u.number,
            path=u.path,
            heading_ru=u.heading_ru,
            heading_kk=u.heading_kk,
            text_ru=u.text_ru,
            text_kk=u.text_kk,
            notes_ru=u.notes_ru,
            notes_kk=u.notes_kk,
            adilet_anchor=u.anchor,
            is_repealed=u.is_repealed,
            ord=u.ord,
        )
        session.add(row)
        await session.flush()
        ids[u.path] = row.id

    await session.commit()
    return LoadResult(src.code, str(version.id), True, len(units), "создана новая редакция")


async def load_historical_version(
    session: AsyncSession,
    src: ActSource,
    units: list[MergedUnit],
    content_hash: str,
    valid_from: date,
    valid_to: date | None,
) -> LoadResult:
    """Историческая редакция: хранится рядом с текущей, не делает её устаревшей.

    Повторная загрузка той же редакции (тот же текст и та же дата начала) ничего не создаёт.
    """
    act = await _upsert_act(session, src)
    existing = (
        await session.execute(
            select(ActVersion).where(ActVersion.act_id == act.id, ActVersion.valid_from == valid_from,
                                     ActVersion.source_hash == content_hash)
        )
    ).scalar_one_or_none()
    if existing is not None:
        await session.commit()
        return LoadResult(src.code, str(existing.id), False, 0, "редакция уже загружена")

    version = ActVersion(act_id=act.id, valid_from=valid_from, valid_to=valid_to, source_hash=content_hash,
                         is_current=False)
    session.add(version)
    await session.flush()
    ids: dict[str, object] = {}
    for u in units:
        row = LegalUnit(
            version_id=version.id, parent_id=ids.get(u.parent_path) if u.parent_path else None,
            unit_type=u.unit_type, number=u.number, path=u.path, heading_ru=u.heading_ru, heading_kk=u.heading_kk,
            text_ru=u.text_ru, text_kk=u.text_kk, notes_ru=u.notes_ru, notes_kk=u.notes_kk,
            adilet_anchor=u.anchor, is_repealed=u.is_repealed, ord=u.ord,
        )
        session.add(row)
        await session.flush()
        ids[u.path] = row.id
    await session.commit()
    return LoadResult(src.code, str(version.id), True, len(units), "историческая редакция загружена")


async def set_current_valid_from(session: AsyncSession, act_code: str, valid_from: date) -> None:
    """Дата начала текущей редакции — по хронологии Adilet, а не по дню скачивания."""
    act = (await session.execute(select(LegalAct).where(LegalAct.code == act_code))).scalar_one()
    await session.execute(
        update(ActVersion).where(ActVersion.act_id == act.id, ActVersion.is_current).values(valid_from=valid_from)
    )
    await session.commit()
