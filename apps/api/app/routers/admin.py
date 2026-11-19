"""Админка: законы и редакции, фоновые задачи, сравнение редакций, проверка ответов юристом, сотрудники."""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select

from app.core.security import hash_password, require_admin, require_staff
from app.db.models import ActVersion, LegalAct, LegalChunk, LegalUnit
from app.db.models.cases import Case, Feedback, Message
from app.db.models.users import User, UserRole
from app.db.session import SessionLocal
from app.services.admin import jobs, tasks
from ingest.sources import ActSource

router = APIRouter(prefix="/admin", tags=["admin"])


def _who(u: User) -> str:
    return u.email or str(u.id)


def _guard(code: str) -> None:
    if code in jobs.busy_acts():
        raise HTTPException(409, f"По акту {code} уже выполняется задача — дождитесь её окончания")


# --- законы ------------------------------------------------------------------------------------

@router.get("/acts")
async def acts(_: User = Depends(require_staff)) -> list[dict]:
    async with SessionLocal() as s:
        rows = (await s.execute(select(LegalAct).order_by(LegalAct.hierarchy_level, LegalAct.code))).scalars().all()
        stats = {r.act_id: r for r in (await s.execute(
            select(ActVersion.act_id, func.count(ActVersion.id).label("n"),
                   func.min(ActVersion.valid_from).label("first"))
            .group_by(ActVersion.act_id))).all()}
        current = {v.act_id: v for v in (await s.execute(select(ActVersion).where(ActVersion.is_current))).scalars().all()}
        chunks = dict((await s.execute(
            select(ActVersion.act_id, func.count(LegalChunk.id))
            .join(LegalUnit, LegalUnit.version_id == ActVersion.id).join(LegalChunk, LegalChunk.unit_id == LegalUnit.id)
            .where(ActVersion.is_current).group_by(ActVersion.act_id))).all())
    busy = jobs.busy_acts()
    return [{
        "code": a.code, "title_ru": a.title_ru, "title_kk": a.title_kk, "act_type": a.act_type,
        "hierarchy_level": a.hierarchy_level, "adilet_id": a.adilet_id, "url": a.adilet_url_ru,
        "versions": stats[a.id].n if a.id in stats else 0,
        "history_from": stats[a.id].first.isoformat() if a.id in stats else None,
        "current_from": current[a.id].valid_from.isoformat() if a.id in current else None,
        "fetched_at": current[a.id].fetched_at.isoformat() if a.id in current else None,
        "chunks": chunks.get(a.id, 0), "busy": a.code in busy,
    } for a in rows]


@router.get("/acts/{code}/versions")
async def versions(code: str, _: User = Depends(require_staff)) -> list[dict]:
    async with SessionLocal() as s:
        act = await s.scalar(select(LegalAct).where(LegalAct.code == code.upper()))
        if act is None:
            raise HTTPException(404, "Акт не найден")
        units = func.count(LegalUnit.id)
        rows = (await s.execute(
            select(ActVersion, units).outerjoin(LegalUnit, LegalUnit.version_id == ActVersion.id)
            .where(ActVersion.act_id == act.id).group_by(ActVersion.id).order_by(ActVersion.valid_from.desc()))).all()
    return [{"id": str(v.id), "valid_from": v.valid_from.isoformat(), "valid_to": v.valid_to.isoformat() if v.valid_to else None,
             "is_current": v.is_current, "units": n, "fetched_at": v.fetched_at.isoformat()} for v, n in rows]


class EditionIn(BaseModel):
    on: date


class AddActIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,30}$")
    adilet_id: str = Field(pattern=r"^[A-Za-z0-9_\-]{6,60}$")
    title_ru: str = Field(min_length=3, max_length=500)
    title_kk: str | None = Field(default=None, max_length=500)
    act_type: Literal["constitution", "code", "law", "gov_decree", "ministry_order", "other"] = "ministry_order"
    hierarchy_level: int = Field(default=5, ge=1, le=7)


@router.post("/acts/{code}/check-updates")
async def check_updates(code: str, user: User = Depends(require_admin)) -> dict:
    code = code.upper()
    _guard(code)
    return jobs.submit("check_updates", f"Проверка обновлений {code}", lambda log: tasks.check_updates(code, log),
                       act_code=code, created_by=_who(user)).public()


@router.post("/acts/check-updates")
async def check_all(user: User = Depends(require_admin)) -> list[dict]:
    async with SessionLocal() as s:
        codes = [c for c in (await s.execute(select(LegalAct.code))).scalars().all() if c not in jobs.busy_acts()]
    return [jobs.submit("check_updates", f"Проверка обновлений {c}", lambda log, c=c: tasks.check_updates(c, log),
                        act_code=c, created_by=_who(user)).public(with_log=False) for c in codes]


@router.post("/acts/{code}/editions")
async def add_edition(code: str, body: EditionIn, user: User = Depends(require_admin)) -> dict:
    code = code.upper()
    _guard(code)
    return jobs.submit("load_edition", f"Редакция {code} на {body.on:%d.%m.%Y}",
                       lambda log: tasks.load_edition(code, body.on, log), act_code=code, created_by=_who(user)).public()


@router.post("/acts/{code}/reindex")
async def reindex(code: str, user: User = Depends(require_admin)) -> dict:
    code = code.upper()
    _guard(code)
    return jobs.submit("reindex", f"Переиндексация {code}", lambda log: tasks.reindex(code, None, log),
                       act_code=code, created_by=_who(user)).public()


@router.delete("/versions/{version_id}")
async def delete_version(version_id: uuid.UUID, user: User = Depends(require_admin)) -> dict:
    async with SessionLocal() as s:
        v = await s.get(ActVersion, version_id)
        act = await s.get(LegalAct, v.act_id) if v else None
    if v is None:
        raise HTTPException(404, "Редакция не найдена")
    if v.is_current:
        raise HTTPException(400, "Действующую редакцию удалить нельзя")
    _guard(act.code)
    return jobs.submit("delete_version", f"Удаление редакции {act.code} с {v.valid_from:%d.%m.%Y}",
                       lambda log: tasks.delete_version(str(version_id), log), act_code=act.code,
                       created_by=_who(user)).public()


@router.post("/acts")
async def add_act(body: AddActIn, user: User = Depends(require_admin)) -> dict:
    src = ActSource(code=body.code, act_type=body.act_type, title_ru=body.title_ru, title_kk=body.title_kk,
                    adilet_id=body.adilet_id, hierarchy_level=body.hierarchy_level)
    _guard(src.code)
    return jobs.submit("add_act", f"Новый акт {src.code}", lambda log: tasks.add_act(src, log),
                       act_code=src.code, created_by=_who(user)).public()


@router.get("/acts/{code}/compare")
async def compare(code: str, d1: date, d2: date, _: User = Depends(require_staff)) -> dict:
    from ingest.compare import compare_data

    async with SessionLocal() as s:
        try:
            return await compare_data(s, code.upper(), d1, d2)
        except SystemExit as e:  # нет редакции на дату
            raise HTTPException(404, str(e)) from e


# --- задачи --------------------------------------------------------------------------------------

@router.get("/jobs")
async def job_list(_: User = Depends(require_staff)) -> list[dict]:
    return jobs.list_jobs()


@router.get("/jobs/{job_id}")
async def job(job_id: str, _: User = Depends(require_staff)) -> dict:
    j = jobs.get_job(job_id)
    if j is None:
        raise HTTPException(404, "Задача не найдена")
    return j.public()


# --- проверка ответов ----------------------------------------------------------------------------

VERDICTS = ("correct", "wrong_norm", "outdated", "incomplete")


class ReviewIn(BaseModel):
    verdict: Literal["correct", "wrong_norm", "outdated", "incomplete"]
    comment: str | None = Field(default=None, max_length=4000)


@router.get("/review")
async def review_list(status: Literal["pending", "flagged", "reviewed", "all"] = "pending", limit: int = 50,
                      _: User = Depends(require_staff)) -> list[dict]:
    async with SessionLocal() as s:
        q = (select(Message, Feedback).outerjoin(Feedback, and_(Feedback.message_id == Message.id,
                                                                Feedback.lawyer_verdict.is_not(None)))
             .where(Message.role == "assistant").order_by(Message.created_at.desc()).limit(min(limit, 200)))
        if status == "pending":
            q = q.where(Feedback.message_id.is_(None))
        elif status == "flagged":
            q = q.where(Message.needs_review.is_(True))
        elif status == "reviewed":
            q = q.where(Feedback.message_id.is_not(None))
        rows = (await s.execute(q)).all()
        case_ids = {m.case_id for m, _ in rows}
        questions: dict = {}
        if case_ids:
            for m in (await s.execute(select(Message).where(Message.case_id.in_(case_ids), Message.role == "user")
                                      .order_by(Message.created_at))).scalars().all():
                questions.setdefault(m.case_id, []).append(m)
    out = []
    for m, fb in rows:
        prior = [u for u in questions.get(m.case_id, []) if u.created_at <= m.created_at]
        ans = m.answer or {}
        meta = ans.get("_meta") or {}
        out.append({
            "id": str(m.id), "case_id": str(m.case_id), "created_at": m.created_at.isoformat(),
            "question": prior[-1].content_raw if prior else None,
            "event_date": (prior[-1].normalized or {}).get("event_date") if prior else None,
            "verdict": ans.get("verdict"), "verdict_text": ans.get("verdict_text"), "summary": ans.get("summary"),
            "legal_answer": ans.get("legal_answer"),
            "legal_basis": [{"act": b.get("act"), "article": b.get("article"), "point": b.get("point"),
                             "quote": b.get("quote"), "quote_verified": b.get("quote_verified", True)}
                            for b in ans.get("legal_basis", [])],
            "mode": meta.get("mode"), "verification": meta.get("verification"), "needs_review": m.needs_review,
            "model": m.model, "lang": m.lang.value if m.lang else None,
            "review": {"verdict": fb.lawyer_verdict, "comment": fb.comment} if fb else None,
        })
    return out


@router.post("/review/{message_id}")
async def review(message_id: uuid.UUID, body: ReviewIn, user: User = Depends(require_staff)) -> dict:
    async with SessionLocal() as s:
        m = await s.get(Message, message_id)
        if m is None or m.role != "assistant":
            raise HTTPException(404, "Ответ не найден")
        fb = await s.get(Feedback, message_id)
        if fb is None:
            fb = Feedback(message_id=message_id)
            s.add(fb)
        fb.lawyer_verdict = body.verdict
        fb.comment = f"[{_who(user)}] {body.comment}" if body.comment else f"[{_who(user)}]"
        m.needs_review = body.verdict != "correct"
        await s.commit()
    return {"ok": True}


@router.get("/stats")
async def stats(_: User = Depends(require_staff)) -> dict:
    async with SessionLocal() as s:
        answers = await s.scalar(select(func.count()).select_from(Message).where(Message.role == "assistant"))
        flagged = await s.scalar(select(func.count()).select_from(Message).where(Message.role == "assistant",
                                                                                Message.needs_review.is_(True)))
        verdicts = dict((await s.execute(select(Feedback.lawyer_verdict, func.count())
                                         .where(Feedback.lawyer_verdict.is_not(None))
                                         .group_by(Feedback.lawyer_verdict))).all())
        cases = await s.scalar(select(func.count()).select_from(Case))
    reviewed = sum(verdicts.values())
    return {"answers": answers, "cases": cases, "flagged": flagged, "reviewed": reviewed, "verdicts": verdicts,
            "accuracy": round(verdicts.get("correct", 0) / reviewed, 3) if reviewed else None}


# --- качество поиска -----------------------------------------------------------------------------

@router.post("/eval/retrieval")
async def eval_retrieval(user: User = Depends(require_admin)) -> dict:
    if "EVAL" in jobs.busy_acts():
        raise HTTPException(409, "Проверка качества уже идёт")
    return jobs.submit("eval", "Проверка качества поиска", tasks.retrieval_eval, act_code="EVAL",
                       created_by=_who(user)).public()


@router.get("/eval/retrieval")
async def eval_latest(_: User = Depends(require_staff)) -> dict | None:
    return tasks.latest_eval()


# --- сотрудники ----------------------------------------------------------------------------------

class UserIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)
    password: str = Field(min_length=8, max_length=200)
    role: Literal["admin", "lawyer"]
    full_name: str | None = Field(default=None, max_length=200)


@router.get("/users")
async def users(_: User = Depends(require_admin)) -> list[dict]:
    async with SessionLocal() as s:
        rows = (await s.execute(select(User).where(User.role.in_([UserRole.admin, UserRole.lawyer]),
                                                   User.deleted_at.is_(None)).order_by(User.created_at))).scalars().all()
    return [{"id": str(u.id), "email": u.email, "full_name": u.full_name, "role": u.role.value} for u in rows]


@router.post("/users")
async def create_user(body: UserIn, _: User = Depends(require_admin)) -> dict:
    email = body.email.strip().lower()
    async with SessionLocal() as s:
        u = await s.scalar(select(User).where(User.email == email))
        if u is not None and u.role in (UserRole.admin, UserRole.lawyer):
            raise HTTPException(409, "Такой сотрудник уже есть")
        if u is None:
            u = User(email=email)
            s.add(u)
        u.password_hash, u.role, u.full_name = hash_password(body.password), UserRole(body.role), body.full_name
        await s.commit()
        return {"id": str(u.id), "email": u.email, "role": u.role.value}


@router.delete("/users/{user_id}")
async def remove_user(user_id: uuid.UUID, me: User = Depends(require_admin)) -> dict:
    if user_id == me.id:
        raise HTTPException(400, "Нельзя удалить себя")
    from datetime import datetime, timezone

    async with SessionLocal() as s:
        u = await s.get(User, user_id)
        if u is None:
            raise HTTPException(404, "Сотрудник не найден")
        u.deleted_at = datetime.now(timezone.utc)
        await s.commit()
    return {"ok": True}
