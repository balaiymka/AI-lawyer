"""Формат ответа AI-юриста (docs/02, раздел B → <output>) и JSON-схема для structured outputs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Шаблоны документов, которые юрист может предложить (Document Builder — Спринт 4).
AVAILABLE_TEMPLATES: dict[str, str] = {
    "flood_act": "Акт о затоплении квартиры",
    "claim_neighbor": "Досудебная претензия соседу о возмещении ущерба",
    "complaint_housing_inspection": "Жалоба в жилищную инспекцию",
    "protocol_copy_request": "Запрос копии протокола собрания собственников",
    "osi_report_request": "Запрос отчёта по управлению объектом кондоминиума",
    "lawsuit_damage": "Исковое заявление о возмещении ущерба",
}


class LegalBasis(BaseModel):
    chunk_id: str
    act: str
    article: str
    point: str
    quote: str
    explanation: str
    quote_verified: bool = True  # проставляет верификатор


class Responsibility(BaseModel):
    party: str
    liability_type: Literal["civil", "administrative", "none", "unclear"]
    reason: str
    citations: list[str] = Field(default_factory=list)


class Assessment(BaseModel):
    position: Literal["strong", "moderate", "weak", "unclear"]
    reasoning: str
    risks: list[str] = Field(default_factory=list)


class ActionStep(BaseModel):
    step: str
    who: str
    where: str
    evidence: list[str] = Field(default_factory=list)
    deadline: str
    citations: list[str] = Field(default_factory=list)


class LawyerAnswer(BaseModel):
    # Вердикт первым: «Вы правы / не правы / частично / зависит от обстоятельств» — на любой вопрос.
    verdict: Literal["yes", "no", "partly", "depends"] = "depends"
    verdict_text: str = ""  # одна фраза: прав ли человек и почему, со ссылкой на норму
    summary: str  # простым языком, для обывателя
    legal_answer: str = ""  # точно и кратко для юриста: квалификация, нормы, редакция
    assumptions: list[str] = Field(default_factory=list)
    legal_basis: list[LegalBasis] = Field(default_factory=list)
    responsibility: list[Responsibility] = Field(default_factory=list)
    assessment: Assessment
    action_plan: list[ActionStep] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)
    clarifying_questions: list[str] = Field(default_factory=list)
    not_found: bool = False
    disclaimer: str


_S = {"type": "string"}
_SL = {"type": "array", "items": _S}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "additionalProperties": False, "properties": props,
            "required": required or list(props)}


LAWYER_SCHEMA = _obj({
    "verdict": {"type": "string", "enum": ["yes", "no", "partly", "depends"]},
    "verdict_text": _S,
    "summary": _S,
    "legal_answer": _S,
    "assumptions": _SL,
    "legal_basis": {"type": "array", "items": _obj({
        "chunk_id": _S, "act": _S, "article": _S, "point": _S, "quote": _S, "explanation": _S})},
    "responsibility": {"type": "array", "items": _obj({
        "party": _S, "liability_type": {"type": "string", "enum": ["civil", "administrative", "none", "unclear"]},
        "reason": _S, "citations": _SL})},
    "assessment": _obj({
        "position": {"type": "string", "enum": ["strong", "moderate", "weak", "unclear"]},
        "reasoning": _S, "risks": _SL}),
    "action_plan": {"type": "array", "items": _obj({
        "step": _S, "who": _S, "where": _S, "evidence": _SL, "deadline": _S, "citations": _SL})},
    "documents": {"type": "array", "items": {"type": "string", "enum": list(AVAILABLE_TEMPLATES)}},
    "clarifying_questions": _SL,
    "not_found": {"type": "boolean"},
    "disclaimer": _S,
})
