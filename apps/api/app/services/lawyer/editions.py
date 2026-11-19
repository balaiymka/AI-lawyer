"""Какая редакция закона применяется к дате события.

Если на дату есть загруженная редакция — она (exact=True). Если нет (история загружена не полностью) —
ближайшая более ранняя загруженная редакция, и ответ честно об этом говорит (exact=False).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from sqlalchemy import func, select

from app.db.models import ActVersion, LegalAct
from app.db.session import SessionLocal


@dataclass
class EditionChoice:
    act_code: str
    event_date: str
    valid_from: str
    valid_to: str | None
    exact: bool
    search_date: date

    def public(self) -> dict:
        d = asdict(self)
        d["search_date"] = self.search_date.isoformat()
        return d


async def resolve_editions(as_of: date) -> list[EditionChoice]:
    """По каждому акту с загруженной историей — какая редакция применяется к дате события."""
    async with SessionLocal() as session:
        temporal = (await session.execute(
            select(LegalAct.id, LegalAct.code).join(ActVersion, ActVersion.act_id == LegalAct.id)
            .group_by(LegalAct.id, LegalAct.code).having(func.count(ActVersion.id) > 1)
            .order_by(LegalAct.hierarchy_level, LegalAct.code))).all()
        out = []
        for t in temporal:
            versions = (await session.execute(
                select(ActVersion).where(ActVersion.act_id == t.id).order_by(ActVersion.valid_from))).scalars().all()
            out.append(_choose(t.code, versions, as_of))
    return out


async def resolve_edition(as_of: date) -> EditionChoice | None:
    choices = await resolve_editions(as_of)
    return next((c for c in choices if c.act_code == "ZHO"), choices[0] if choices else None)


def _choose(code: str, versions: list, as_of: date) -> EditionChoice:
    covering = [v for v in versions if v.valid_from <= as_of and (v.valid_to is None or as_of < v.valid_to)]
    if covering:
        v, exact, search = covering[-1], True, as_of
    else:
        earlier = [v for v in versions if v.valid_from <= as_of]
        v = earlier[-1] if earlier else versions[0]
        exact, search = False, v.valid_from
    return EditionChoice(code, as_of.isoformat(), v.valid_from.isoformat(),
                         v.valid_to.isoformat() if v.valid_to else None, exact, search)
