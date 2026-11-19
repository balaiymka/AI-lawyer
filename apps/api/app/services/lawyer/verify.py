"""Верификатор ответа: модель может ссылаться только на пункты из <context>.

* ссылка на chunk_id, которого нет в контексте, удаляется (или привязывается к пункту с тем же номером);
* номер статьи/пункта и название акта берутся из контекста, а не из ответа модели;
* цитата должна дословно (с точностью до пробелов и кавычек) входить в текст пункта —
  иначе она заменяется настоящим текстом пункта и помечается quote_verified=false;
* статьи, упомянутые в свободном тексте, но отсутствующие в контексте, попадают в unverified_refs
  (ответ помечается needs_review).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from app.services.lawyer.context import ContextChunk
from app.services.lawyer.schema import LawyerAnswer
from app.services.rag.refs import extract_refs

QUOTE_MAX = 400


@dataclass
class Verification:
    removed_citations: list[str] = field(default_factory=list)
    replaced_quotes: int = 0
    unverified_refs: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return bool(self.removed_citations or self.replaced_quotes or self.unverified_refs)

    def dict(self) -> dict:
        return {**asdict(self), "needs_review": self.needs_review}


def _norm(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[«»\"“”„'`]", "", s)
    s = re.sub(r"\.{3}|…", " ", s)
    return re.sub(r"\s+", " ", s).strip(" .;:,")


def _quote_ok(quote: str, texts: dict[str, str]) -> bool:
    q = _norm(quote)
    if len(q) < 10:
        return False
    # Модель может сокращать цитату многоточием — проверяем каждый фрагмент отдельно.
    pieces = [p for p in (_norm(x) for x in re.split(r"\.{3}|…", quote)) if len(p) >= 10] or [q]
    return any(all(p in _norm(t) for p in pieces) for t in texts.values())


def _excerpt(text: str) -> str:
    return text if len(text) <= QUOTE_MAX else text[: QUOTE_MAX - 1].rsplit(" ", 1)[0] + "…"


def verify_answer(answer: LawyerAnswer, chunks: list[ContextChunk]) -> tuple[LawyerAnswer, Verification]:
    v = Verification()
    by_id: dict[str, ContextChunk] = {}
    for c in chunks:
        by_id[c.chunk_id] = c
    by_ref = {(c.article, c.point or ""): c for c in chunks}

    def resolve(cid: str) -> ContextChunk | None:
        return by_id.get(cid)

    basis = []
    for b in answer.legal_basis:
        c = resolve(b.chunk_id) or by_ref.get((b.article, b.point or ""))
        if c is None:
            v.removed_citations.append(b.chunk_id or f"ст.{b.article} п.{b.point}")
            continue
        b.chunk_id, b.act, b.article, b.point = c.chunk_id, c.act_title, c.article or "", c.point or ""
        if not _quote_ok(b.quote, c.texts):
            b.quote, b.quote_verified = _excerpt(c.text), False
            v.replaced_quotes += 1
        basis.append(b)
    answer.legal_basis = basis

    def keep(ids: list[str]) -> list[str]:
        ok = [i for i in ids if i in by_id]
        v.removed_citations.extend(i for i in ids if i not in by_id)
        return ok

    for r in answer.responsibility:
        r.citations = keep(r.citations)
    for s in answer.action_plan:
        s.citations = keep(s.citations)

    # Статьи, названные в тексте ответа, должны быть среди найденных.
    known = {c.article for c in chunks}
    free_text = " ".join([answer.verdict_text, answer.summary, answer.legal_answer, answer.assessment.reasoning, *answer.assumptions, *answer.assessment.risks,
                          *(f"{s.step} {s.deadline}" for s in answer.action_plan),
                          *(f"{r.reason}" for r in answer.responsibility),
                          *(b.explanation for b in answer.legal_basis)])
    for ref in extract_refs(free_text):
        if ref.article not in known and ref.article not in v.unverified_refs:
            v.unverified_refs.append(ref.article)

    if not answer.legal_basis and not answer.not_found and not chunks:
        answer.not_found = True
    return answer, v
