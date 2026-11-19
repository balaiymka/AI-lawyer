"""Сравнение двух редакций акта: какие статьи/пункты появились, исчезли, изменились.

  python -m ingest.compare ZHO 2018-01-01 2026-11-16 [--out docs/...md]

Редакции выбираются по дате (действовавшая в тот день). Сравнение по `path` (art42/p8) и тексту ru.
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import and_, or_, select

from app.db.models import ActVersion, LegalAct, LegalUnit
from app.db.session import SessionLocal, engine


@dataclass
class Unit:
    path: str
    unit_type: str
    number: str | None
    heading: str | None
    text: str
    repealed: bool


def _norm(t: str | None) -> str:
    t = re.sub(r"\s+", " ", (t or "")).strip()
    return re.sub(r"^\d+(-\d+)*[.)]\s*", "", t)


async def _version_at(session, code: str, when: date):
    q = (select(ActVersion, LegalAct).join(LegalAct, LegalAct.id == ActVersion.act_id)
         .where(LegalAct.code == code, ActVersion.valid_from <= when,
                or_(ActVersion.valid_to.is_(None), ActVersion.valid_to > when))
         .order_by(ActVersion.valid_from.desc()))
    row = (await session.execute(q)).first()
    if row is None:
        raise SystemExit(f"Нет загруженной редакции {code} на {when}")
    return row


async def _units(session, version_id) -> dict[str, Unit]:
    rows = (await session.execute(select(LegalUnit).where(LegalUnit.version_id == version_id))).scalars().all()
    return {u.path: Unit(u.path, u.unit_type, u.number, u.heading_ru, _norm(u.text_ru), u.is_repealed) for u in rows}


def article_of(path: str) -> str | None:
    m = re.match(r"(art[\d-]+)", path)
    return m.group(1) if m else None


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


async def compare(code: str, d1: date, d2: date) -> str:
    async with SessionLocal() as session:
        data = await compare_data(session, code, d1, d2)
    await engine.dispose()
    return to_markdown(data)


async def compare_data(session, code: str, d1: date, d2: date) -> dict:
    """Структурированное сравнение двух редакций (для админки и для отчёта)."""
    v1, act = await _version_at(session, code, d1)
    v2, _ = await _version_at(session, code, d2)
    a, b = await _units(session, v1.id), await _units(session, v2.id)

    arts_a = {p: u for p, u in a.items() if u.unit_type == "article"}
    arts_b = {p: u for p, u in b.items() if u.unit_type == "article"}
    new_arts = [p for p in arts_b if p not in arts_a and not arts_b[p].repealed]
    gone_arts = [p for p in arts_a if p not in arts_b or (arts_b[p].repealed and not arts_a[p].repealed)]

    changed: dict[str, list[tuple[str, str, float]]] = defaultdict(list)  # статья → [(путь, вид, сходство)]
    for p, ub in b.items():
        if ub.unit_type not in ("point", "article") or ub.repealed:
            continue
        art = article_of(p)
        if art in new_arts:
            continue
        ua = a.get(p)
        if ua is None:
            changed[art or p].append((p, "добавлен", 0.0))
        elif ua.text != ub.text:
            sim = similarity(ua.text, ub.text)
            if sim < 0.97:  # мелкие правки (запятая, «Республики Казахстан») не считаем
                changed[art or p].append((p, "изменён", sim))
    for p, ua in a.items():
        if ua.unit_type == "point" and p not in b and article_of(p) not in gone_arts:
            changed[article_of(p) or p].append((p, "исключён", 0.0))

    def title(p: str, src: dict[str, Unit]) -> str:
        u = src.get(p)
        n = p.removeprefix("art")
        return f"Статья {n}" + (f". {u.heading}" if u and u.heading else "")

    total_points_a = sum(1 for u in a.values() if u.unit_type == "point" and not u.repealed)
    total_points_b = sum(1 for u in b.values() if u.unit_type == "point" and not u.repealed)
    ranked = sorted(changed.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    def counts(items):
        k = defaultdict(int)
        for _, kind, _ in items:
            k[kind] += 1
        return {"changed": k["изменён"], "added": k["добавлен"], "removed": k["исключён"]}

    return {
        "act": act.code, "title": act.title_ru, "d1": d1.isoformat(), "d2": d2.isoformat(),
        "from_version": {"valid_from": v1.valid_from.isoformat(), "valid_to": v1.valid_to.isoformat() if v1.valid_to else None},
        "to_version": {"valid_from": v2.valid_from.isoformat(), "valid_to": v2.valid_to.isoformat() if v2.valid_to else None},
        "stats": {
            "articles_before": len([1 for u in arts_a.values() if not u.repealed]),
            "articles_after": len([1 for u in arts_b.values() if not u.repealed]),
            "points_before": total_points_a, "points_after": total_points_b,
            "new_articles": len(new_arts), "removed_articles": len(gone_arts), "changed_articles": len(changed),
        },
        "new_articles": [{"path": p, "title": title(p, b)} for p in sorted(new_arts, key=_sort_key)],
        "removed_articles": [{"path": p, "title": title(p, a)} for p in sorted(gone_arts, key=_sort_key)],
        "changed_articles": [{"path": art, "title": title(art, b) if art in b else title(art, a), **counts(items)}
                             for art, items in ranked[:60]],
    }


def to_markdown(d: dict) -> str:
    st = d["stats"]
    lines = [
        f"# {d['title']}: что изменилось с {_ru(d['d1'])} по {_ru(d['d2'])}", "",
        f"Сравниваются редакции: **с {_ru(d['from_version']['valid_from'])}** и **с {_ru(d['to_version']['valid_from'])}**. "
        "Источник — хронология редакций adilet.zan.kz.", "",
        "| | Было | Стало |", "|---|---|---|",
        f"| Статей | {st['articles_before']} | {st['articles_after']} |",
        f"| Пунктов | {st['points_before']} | {st['points_after']} |",
        f"| Новых статей | — | {st['new_articles']} |",
        f"| Исключённых статей | {st['removed_articles']} | — |",
        f"| Статей с существенно изменёнными пунктами | — | {st['changed_articles']} |", "",
        "## Новые статьи", "", *[f"- {x['title']}" for x in d["new_articles"]], "",
        "## Исключённые статьи", "", *([f"- {x['title']}" for x in d["removed_articles"]] or ["- нет"]), "",
        "## Статьи с наибольшими изменениями", "", "| Статья | Пунктов изменено / добавлено / исключено |", "|---|---|",
        *[f"| {x['title']} | {x['changed']} / {x['added']} / {x['removed']} |" for x in d["changed_articles"][:40]],
    ]
    return "\n".join(lines) + "\n"


def _ru(iso: str) -> str:
    y, m, dd = iso.split("-")
    return f"{dd}.{m}.{y}"


def _sort_key(p: str):
    nums = [int(x) for x in re.findall(r"\d+", p)]
    return nums


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("d1")
    ap.add_argument("d2")
    ap.add_argument("--out")
    args = ap.parse_args()
    report = asyncio.run(compare(args.code.upper(), date.fromisoformat(args.d1), date.fromisoformat(args.d2)))
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"→ {args.out}")
    else:
        print(report)


if __name__ == "__main__":
    main()
