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
    out_of_scope: list[str] = field(default_factory=list)  # нормы особого режима, убранные из оснований

    @property
    def needs_review(self) -> bool:
        return bool(self.removed_citations or self.replaced_quotes or self.unverified_refs or self.out_of_scope)

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


def verify_answer(answer: LawyerAnswer, chunks: list[ContextChunk],
                  question: str | None = None) -> tuple[LawyerAnswer, Verification]:
    v = Verification()
    if question:
        # Последний рубеж после фактчека: норму особого режима (ЖСК, госжилфонд…), не относящуюся к ситуации,
        # убираем из оснований и ссылок, даже если модель не исправила это сама.
        bad = {c.chunk_id for c in chunks for h, t, _ in SPECIAL_REGIMES if h.search(c.breadcrumb) and not t.search(question)}
        dropped = [b for b in answer.legal_basis if b.chunk_id in bad]
        if dropped:
            v.out_of_scope = [f"ст. {b.article}" + (f" п. {b.point}" if b.point else "") for b in dropped]
            answer.legal_basis = [b for b in answer.legal_basis if b.chunk_id not in bad]
            for group in (answer.responsibility, answer.action_plan, answer.calculations, answer.attention):
                for item in group:
                    item.citations = [c for c in item.citations if c not in bad]
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
    for c in answer.calculations:
        c.citations = keep(c.citations)
    for a in answer.attention:
        a.citations = keep(a.citations)

    # Статьи, названные в тексте ответа, должны быть среди найденных.
    v.unverified_refs = unverified_refs(answer, chunks)

    if not answer.legal_basis and not answer.not_found and not chunks:
        answer.not_found = True
    return answer, v


def unverified_refs(answer: LawyerAnswer, chunks: list[ContextChunk]) -> list[str]:
    """Номера статей из свободного текста ответа, которых нет среди найденных норм.

    Это детерминированная проверка, не зависящая от мнения модели: такой номер мог быть взят «по памяти»
    (или из нормы другого акта) и не подтверждён текстом в <context>.
    """
    known = {c.article for c in chunks}
    free_text = " ".join([answer.verdict_text, answer.summary, answer.legal_answer, answer.assessment.reasoning,
                          *answer.assumptions, *answer.assessment.risks,
                          *(f"{s.step} {s.deadline}" for s in answer.action_plan),
                          *(f"{r.reason}" for r in answer.responsibility),
                          *(b.explanation for b in answer.legal_basis),
                          *(f"{c.rule} {c.result}" for c in answer.calculations),
                          *(f"{a.point} {a.why}" for a in answer.attention)])
    out: list[str] = []
    for ref in extract_refs(free_text):
        if ref.article not in known and ref.article not in out:
            out.append(ref.article)
    return out


# Особые правовые режимы ЗЖО: нормы из этих глав/статей применяются только к своим субъектам.
# (шаблон заголовка во фрагменте, слова в вопросе, при которых режим уместен, название режима)
SPECIAL_REGIMES = [
    (re.compile(r"жилищно-строительн\w* кооператив", re.I), re.compile(r"ЖСК|кооператив", re.I),
     "жилищно-строительный кооператив"),
    (re.compile(r"государственного жилищного фонда|арендованн\w* местным исполнительным органом", re.I),
     re.compile(r"госжил|государствен\w* (жил|фонд|квартир)|коммунальн\w* (жиль|квартир|фонд)|акимат\w* (квартир|жиль)|"
                r"очеред|социальн\w* жиль|арендн\w* жиль\w* (от )?акимат", re.I),
     "жильё из государственного жилищного фонда"),
    (re.compile(r"служебн\w* жилищ", re.I), re.compile(r"служебн", re.I), "служебное жильё"),
    (re.compile(r"общежити", re.I), re.compile(r"общежит|жатақхана", re.I), "общежитие"),
]


def scope_mismatches(answer: LawyerAnswer, chunks: list[ContextChunk], question: str) -> list[tuple[str, str]]:
    """Нормы особого режима, на которые опирается ответ, хотя в вопросе нет признаков этого режима.

    Детерминированная проверка сферы действия: модель видит заголовок «Прекращение деятельности ЖСК», но
    всё равно применяет норму к обычному застройщику. Возвращает [(статья, режим)].
    """
    by_id = {c.chunk_id: c for c in chunks}
    cited = {b.chunk_id for b in answer.legal_basis}
    out: list[tuple[str, str]] = []
    for cid in cited:
        c = by_id.get(cid)
        if c is None:
            continue
        for heading, trigger, name in SPECIAL_REGIMES:
            if heading.search(c.breadcrumb) and not trigger.search(question):
                ref = f"ст. {c.article}" + (f" п. {c.point}" if c.point else "")
                if (ref, name) not in out:
                    out.append((ref, name))
    return out
