"""Нарезка юридических единиц на чанки для поиска.

Единица чанка — юридическая единица, а не окно в N токенов:
  * пункт статьи (вместе со своими подпунктами);
  * подпункт, стоящий прямо под статьёй без пунктов (так устроены определения ст. 2 ЗЖО);
  * собственный текст статьи (вступление или вся статья, если в ней нет пунктов);
  * у длинных пунктов (> LONG_POINT_CHARS) дополнительно — каждый подпункт с вводной фразой пункта,
    чтобы точнее находить, например, «кто может инициировать собрание» внутри большого перечня.

Каждый чанк начинается с «хлебных крошек» (акт › глава › статья › пункт): эмбеддинг знает, откуда кусок.
Исключённые/утратившие силу единицы не индексируются.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

LONG_POINT_CHARS = 1500


@dataclass
class UnitRow:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    unit_type: str
    number: str | None
    path: str
    heading_ru: str | None = None
    heading_kk: str | None = None
    text_ru: str | None = None
    text_kk: str | None = None
    is_repealed: bool = False
    ord: int = 0


@dataclass
class ActInfo:
    code: str
    title_ru: str
    title_kk: str | None


@dataclass
class ChunkDraft:
    unit_id: uuid.UUID
    lang: str  # 'ru' | 'kk'
    breadcrumb: str
    content: str  # breadcrumb + текст — то, что эмбеддится и показывается модели
    # Метаданные для payload Qdrant
    act_code: str = ""
    path: str = ""
    article: str | None = None
    point: str | None = None
    kind: str = "point"  # point | subpoint | article
    extra: dict = field(default_factory=dict)


def _label(u: UnitRow, lang: str) -> str:
    n = u.number or ""
    heading = u.heading_ru if lang == "ru" else (u.heading_kk or u.heading_ru)
    if lang == "ru":
        names = {"section": f"Раздел {n}", "chapter": f"Глава {n}", "paragraph": f"Параграф {n}",
                 "article": f"Статья {n}", "point": f"п. {n}", "subpoint": f"пп. {n})"}
    else:
        names = {"section": f"{n}-бөлім", "chapter": f"{n}-тарау", "paragraph": f"{n}-параграф",
                 "article": f"{n}-бап", "point": f"{n}-тармақ", "subpoint": f"{n})-тармақша"}
    base = names.get(u.unit_type, n)
    return f"{base}. {heading}" if heading and u.unit_type in ("chapter", "paragraph", "article") else base


def build_chunks(units: list[UnitRow], act: ActInfo) -> list[ChunkDraft]:
    by_id = {u.id: u for u in units}
    children: dict[uuid.UUID | None, list[UnitRow]] = {}
    for u in sorted(units, key=lambda x: x.ord):
        children.setdefault(u.parent_id, []).append(u)

    def ancestors(u: UnitRow) -> list[UnitRow]:
        chain = []
        cur = by_id.get(u.parent_id) if u.parent_id else None
        while cur is not None:
            chain.append(cur)
            cur = by_id.get(cur.parent_id) if cur.parent_id else None
        return list(reversed(chain))

    def article_of(u: UnitRow) -> UnitRow | None:
        for a in [u, *reversed(ancestors(u))]:
            if a.unit_type == "article":
                return a
        return None

    def crumb(u: UnitRow, lang: str) -> str:
        title = act.title_ru if lang == "ru" else (act.title_kk or act.title_ru)
        parts = [title] + [_label(a, lang) for a in ancestors(u) if a.unit_type in ("chapter", "article", "point")]
        parts.append(_label(u, lang))
        return " › ".join(parts)

    def text(u: UnitRow, lang: str) -> str | None:
        return u.text_ru if lang == "ru" else u.text_kk

    def make(u: UnitRow, lang: str, body: str, kind: str, point: str | None) -> ChunkDraft:
        art = article_of(u)
        bc = crumb(u, lang)
        return ChunkDraft(
            unit_id=u.id, lang=lang, breadcrumb=bc, content=f"{bc}\n{body}", act_code=act.code,
            path=u.path, article=art.number if art else None, point=point, kind=kind,
        )

    # Приказы с Правилами/Методикой не делятся на статьи: берём пункты внутри глав. Текст самого приказа
    # («1. Утвердить Правила…») и бланки форм из приложений (пункты вне глав) в поиск не попадают.
    has_articles = any(u.unit_type == "article" for u in units)

    def in_chapter(u: UnitRow) -> bool:
        return any(a.unit_type == "chapter" for a in ancestors(u))

    chunks: list[ChunkDraft] = []
    for u in sorted(units, key=lambda x: x.ord):
        if u.is_repealed:
            continue
        art = article_of(u)
        if has_articles and (art is None or art.is_repealed):
            continue
        if not has_articles and (not in_chapter(u) or "~" in u.path):
            continue  # «~» — повтор нумерации: это бланк формы внутри главы, а не пункт Правил
        parent = by_id.get(u.parent_id) if u.parent_id else None
        for lang in ("ru", "kk"):
            body = text(u, lang)
            if not body or sum(ch.isalpha() for ch in body) < 25:  # пустые строки бланков «1.______»
                continue
            if body.count("_") > 15 or "(подпись)" in body.lower() or "(қолы)" in body.lower():
                continue  # строки для заполнения и подписи в бланках
            if u.unit_type == "article":
                chunks.append(make(u, lang, body, "article", None))
            elif u.unit_type == "point":
                chunks.append(make(u, lang, body, "point", u.number))
            elif u.unit_type == "subpoint" and parent is not None:
                if parent.unit_type == "article":
                    chunks.append(make(u, lang, body, "subpoint", None))
                elif parent.unit_type == "point":
                    parent_text = text(parent, lang) or ""
                    if len(parent_text) > LONG_POINT_CHARS:
                        intro = parent_text.splitlines()[0]
                        chunks.append(make(u, lang, f"{intro}\n{body}", "subpoint", parent.number))
    return chunks
