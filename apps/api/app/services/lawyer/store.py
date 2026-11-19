"""Сохранение диалога: дело → сообщения пользователя и юриста → цитаты → трасса поиска.

Пока нет входа в аккаунт, все дела пишутся на одного гостевого пользователя.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.db.models.cases import Case, Message, MessageCitation, RetrievalTrace
from app.db.models.users import Lang, User
from app.db.session import SessionLocal
from app.services.lawyer.context import ContextChunk

GUEST_EMAIL = "guest@zhkh24.local"


async def _guest_id(session) -> uuid.UUID:
    uid = await session.scalar(select(User.id).where(User.email == GUEST_EMAIL))
    if uid is None:
        user = User(email=GUEST_EMAIL, full_name="Гость")
        session.add(user)
        await session.flush()
        uid = user.id
    return uid


async def save_exchange(*, case_id: str | None, text: str, normalized: dict, answer: dict, reply_lang: str,
                        chunks: list[ContextChunk], cited: set[str], model: str | None, usage: dict | None,
                        needs_review: bool, queries: list[str], candidates: int, latency_ms: dict,
                        meta: dict | None = None) -> str:
    async with SessionLocal() as session:
        case = await session.get(Case, uuid.UUID(case_id)) if case_id else None
        if case is None:
            case = Case(user_id=await _guest_id(session), title=text[:120], category=normalized.get("category"))
            session.add(case)
            await session.flush()

        lang = Lang(reply_lang)
        session.add(Message(case_id=case.id, role="user", content_raw=text, normalized=normalized, lang=lang))
        reply = Message(case_id=case.id, role="assistant", answer={**answer, "_meta": meta or {}}, lang=lang,
                        model=model, usage=usage,
                        needs_review=needs_review)
        session.add(reply)
        await session.flush()

        by_id = {c.chunk_id: c for c in chunks}
        for cid in cited:
            c = by_id.get(cid)
            if c:
                session.add(MessageCitation(message_id=reply.id, chunk_id=uuid.UUID(cid), unit_id=uuid.UUID(c.unit_id),
                                            verified=True))
        session.add(RetrievalTrace(message_id=reply.id, queries={"queries": queries},
                                   candidates={"count": candidates, "context": [c.path for c in chunks]},
                                   latency_ms=latency_ms))
        await session.commit()
        return str(case.id)


async def load_case(case_id: str) -> dict | None:
    async with SessionLocal() as session:
        case = await session.get(Case, uuid.UUID(case_id))
        if case is None:
            return None
        rows = (await session.scalars(
            select(Message).where(Message.case_id == case.id).order_by(Message.created_at))).all()
        return {"id": str(case.id), "title": case.title, "category": case.category,
                "messages": [{"role": m.role, "text": m.content_raw, "answer": m.answer,
                              "lang": m.lang.value if m.lang else None} for m in rows]}


async def list_cases(limit: int = 30) -> list[dict]:
    """Дела гостевого пользователя, новые сверху (до появления входа в аккаунт)."""
    async with SessionLocal() as session:
        guest = await session.scalar(select(User.id).where(User.email == GUEST_EMAIL))
        if guest is None:
            return []
        last = func.max(Message.created_at).label("last")
        rows = (await session.execute(
            select(Case.id, Case.title, Case.category, last, func.count(Message.id).label("n"))
            .join(Message, Message.case_id == Case.id)
            .where(Case.user_id == guest)
            .group_by(Case.id).order_by(last.desc()).limit(limit))).all()
        return [{"id": str(r.id), "title": r.title, "category": r.category, "updated_at": r.last.isoformat(),
                 "turns": r.n // 2} for r in rows]
