"""Справочник НПА (минимальная версия Спринта 0–1: список актов и статья по номеру)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActVersion, LegalAct, LegalUnit
from app.db.session import get_session

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/acts")
async def list_acts(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (await session.execute(select(LegalAct).order_by(LegalAct.hierarchy_level, LegalAct.code))).scalars()
    return [
        {"code": a.code, "title_ru": a.title_ru, "title_kk": a.title_kk, "number": a.number, "status": a.status,
         "act_type": a.act_type, "hierarchy_level": a.hierarchy_level}
        for a in rows
    ]


async def _current_version(session: AsyncSession, code: str) -> ActVersion:
    version = (
        await session.execute(
            select(ActVersion)
            .join(LegalAct, LegalAct.id == ActVersion.act_id)
            .where(LegalAct.code == code.upper(), ActVersion.is_current)
        )
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(404, "Акт не загружен")
    return version


@router.get("/acts/{code}/toc")
async def get_toc(code: str, session: AsyncSession = Depends(get_session)) -> dict:
    """Оглавление: разделы, главы, параграфы и статьи (без текста)."""
    version = await _current_version(session, code)
    act = await session.get(LegalAct, version.act_id)
    units = (
        await session.execute(
            select(LegalUnit.unit_type, LegalUnit.number, LegalUnit.path, LegalUnit.heading_ru, LegalUnit.heading_kk,
                   LegalUnit.is_repealed)
            .where(LegalUnit.version_id == version.id)
            .where(LegalUnit.unit_type.in_(("section", "chapter", "paragraph", "article")))
            .order_by(LegalUnit.ord)
        )
    ).all()
    return {
        "act": act.code, "title_ru": act.title_ru, "title_kk": act.title_kk,
        "url_ru": act.adilet_url_ru, "url_kk": act.adilet_url_kk, "valid_from": version.valid_from.isoformat(),
        "items": [{"type": u.unit_type, "number": u.number, "path": u.path, "heading_ru": u.heading_ru,
                   "heading_kk": u.heading_kk, "is_repealed": u.is_repealed} for u in units],
    }


@router.get("/acts/{code}/articles/{number}")
async def get_article(code: str, number: str, session: AsyncSession = Depends(get_session)) -> dict:
    version = await _current_version(session, code)

    if number.startswith("ch"):
        return await _chapter(session, code, version, number)
    prefix = f"art{number}"
    units = (
        await session.execute(
            select(LegalUnit)
            .where(LegalUnit.version_id == version.id)
            .where((LegalUnit.path == prefix) | LegalUnit.path.startswith(prefix + "/"))
            .where(LegalUnit.unit_type != "subpoint")  # подпункты уже входят в текст пункта
            .order_by(LegalUnit.ord)
        )
    ).scalars().all()
    if not units:
        raise HTTPException(404, "Статья не найдена")

    article, *children = units
    return {
        "act": code.upper(),
        "number": article.number,
        "heading_ru": article.heading_ru,
        "heading_kk": article.heading_kk,
        "notes_ru": article.notes_ru,
        "notes_kk": article.notes_kk,
        "is_repealed": article.is_repealed,
        "valid_from": version.valid_from.isoformat(),
        "units": [
            {"path": u.path, "type": u.unit_type, "number": u.number, "text_ru": u.text_ru, "text_kk": u.text_kk}
            for u in children
        ],
    }


async def _chapter(session: AsyncSession, code: str, version: ActVersion, path: str) -> dict:
    """Глава акта без статей (Правила, Методика): глава и её пункты."""
    chapter = (
        await session.execute(
            select(LegalUnit).where(LegalUnit.version_id == version.id, LegalUnit.path == path)
        )
    ).scalar_one_or_none()
    if chapter is None or chapter.unit_type != "chapter":
        raise HTTPException(404, "Глава не найдена")
    points = (
        await session.execute(
            select(LegalUnit)
            .where(LegalUnit.version_id == version.id, LegalUnit.parent_id == chapter.id, LegalUnit.unit_type == "point")
            .order_by(LegalUnit.ord)
        )
    ).scalars().all()
    return {
        "act": code.upper(), "number": path, "kind": "chapter",
        "heading_ru": chapter.heading_ru, "heading_kk": chapter.heading_kk,
        "notes_ru": chapter.notes_ru, "notes_kk": chapter.notes_kk,
        "is_repealed": chapter.is_repealed, "valid_from": version.valid_from.isoformat(),
        "units": [{"path": u.path, "type": u.unit_type, "number": u.number, "text_ru": u.text_ru,
                   "text_kk": u.text_kk} for u in points],
    }
