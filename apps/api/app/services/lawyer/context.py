"""Блок <context> для AI-юриста: найденные пункты закона с атрибутами для цитирования."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from xml.sax.saxutils import escape, quoteattr

from app.services.rag.retriever import Result


@lru_cache
def _acts():
    from ingest.sources import load_sources

    return load_sources()


@dataclass
class ContextChunk:
    chunk_id: str  # id чанка на языке, который видит модель
    unit_id: str
    act_code: str
    act_title: str
    article: str | None
    point: str | None
    path: str
    lang: str
    text: str  # текст без строки-«хлебных крошек»
    texts: dict[str, str]  # {lang: текст} — для проверки цитат на любом языке
    breadcrumb: str
    version_date: str | None
    url: str | None
    valid_to: str | None = None
    is_current: bool = True
    hierarchy_level: int | None = None
    xref_from: str | None = None  # фрагмент добавлен, потому что на него ссылается найденная норма (путь ссылающейся)
    relation: str | None = None  # связь по графу закона: exception | reference | exception_for | rule_for_list | referenced_by

    def public(self) -> dict:
        return {k: getattr(self, k) for k in ("chunk_id", "unit_id", "act_code", "act_title", "article", "point",
                                              "path", "lang", "text", "breadcrumb", "version_date", "url",
                                              "valid_to", "is_current", "hierarchy_level", "xref_from", "relation")}

    @property
    def edition(self) -> str:
        if self.is_current or not self.version_date:
            return f"действующая редакция (с {self.version_date})" if self.version_date else "действующая редакция"
        return f"редакция, действовавшая с {self.version_date} по {self.valid_to or '…'}"


LEVELS = {1: "1 — Конституция", 2: "2 — кодекс", 3: "3 — закон", 4: "4 — постановление Правительства",
          5: "5 — приказ министра (правила, методика)"}


# Как связанный пункт относится к найденному (linked_to — путь найденного пункта).
RELATIONS = {
    "exception": "найденная норма делает исключение для этого пункта (за исключением / кроме)",
    "reference": "найденная норма отсылает к этому пункту",
    "exception_for": "этот пункт делает исключение для найденного: по нему действует особое правило",
    "rule_for_list": "этот пункт задаёт правило для перечня, в который входит найденный подпункт "
                     "(общее правило + исключения для части подпунктов)",
    "condition": "найденная норма применяется в случаях / при условиях, указанных в этом пункте",
    "procedure": "найденная норма отсылает к этому пункту за порядком (процедурой)",
    "condition_for": "этот пункт ставит условие применения найденного",
    "procedure_for": "этот пункт устанавливает порядок со ссылкой на найденный",
    "referenced_by": "этот пункт ссылается на найденный",
}


def _body(content: str) -> str:
    # content = "хлебные крошки\nтекст"
    return content.split("\n", 1)[1] if "\n" in content else content


def build_context(results: list[Result], reply_lang: str) -> tuple[str, list[ContextChunk]]:
    chunks: list[ContextChunk] = []
    for r in results:
        lang = reply_lang if reply_lang in r.contents else next(iter(r.contents))
        src = _acts().get(r.act_code)
        title = (src.title_kk if lang == "kk" and src and src.title_kk else src.title_ru) if src else r.act_code
        chunks.append(ContextChunk(
            chunk_id=r.chunk_ids[lang], unit_id=r.unit_id, act_code=r.act_code, act_title=title,
            article=r.article, point=r.meta.get("point"), path=r.path, lang=lang,
            text=_body(r.contents[lang]), texts={k: _body(v) for k, v in r.contents.items()},
            breadcrumb=r.meta.get(f"breadcrumb_{lang}") or "", version_date=r.meta.get("valid_from"),
            url=src.url(lang) if src else None, valid_to=r.meta.get("valid_to"),
            is_current=r.meta.get("is_current", True) is not False,
            hierarchy_level=src.hierarchy_level if src else None, xref_from=r.meta.get("xref_from"),
            relation=r.meta.get("relation"),
        ))

    parts = ["<context>"]
    for c in chunks:
        attrs = " ".join(f"{k}={quoteattr(str(v or ''))}" for k, v in (
            ("chunk_id", c.chunk_id), ("act", c.act_title), ("article", c.article), ("point", c.point),
            ("version_date", c.version_date), ("edition", c.edition), ("level", LEVELS.get(c.hierarchy_level or 0, "")),
            ("url", c.url)))
        if c.relation:
            attrs += (f" role=\"linked_norm\" relation={quoteattr(RELATIONS.get(c.relation, c.relation))}"
                      f" linked_to={quoteattr(c.xref_from or '')}")
        elif c.xref_from:
            attrs += f" role=\"cross_reference\" referenced_from={quoteattr(c.xref_from)}"
        parts.append(f"<chunk {attrs}>\n{escape(c.breadcrumb)}\n{escape(c.text)}\n</chunk>")
    parts.append("</context>")
    return "\n".join(parts), chunks
