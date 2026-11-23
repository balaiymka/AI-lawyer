"""Многошаговая консультация: ветки по подвопросам и фактчек готового ответа.

1. Сообщение «у меня 100 квартир, хочу выбрать председателя, утвердить тариф и поставить антенну, составь
   вопросы и подскажи кворум» нормализатор делит на подвопросы (sub_questions).
2. Каждый подвопрос ищется отдельно (свои нормы) и разбирается своей веткой — analyze_branch().
3. Итоговый ответ собирается из всех веток (generator, блок <branch_analyses>).
4. fact_check() перечитывает ответ против норм: цифры, пороги, исключения, арифметика, все ли подвопросы
   отвечены. Если есть замечания — ответ переписывается один раз (pipeline).
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.lawyer.generator import JSON_INSTRUCTIONS, LawyerError, _extract_json, llm_provider

log = logging.getLogger(__name__)
PROMPTS = Path(__file__).parents[2] / "prompts"

_S = {"type": "string"}
_SL = {"type": "array", "items": _S}


def _obj(props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "properties": props, "required": list(props)}


class BranchAnalysis(BaseModel):
    question: str = ""
    kind: str = "legal"
    answer: str = ""  # вывод по подвопросу
    rule: str = ""  # какое правило применяется, с исключениями
    calculation: str = ""  # арифметика на числах пользователя
    draft: str = ""  # текст, если просили составить
    citations: list[str] = Field(default_factory=list)
    missing: str = ""  # чего не хватает в найденных нормах


BRANCH_SCHEMA = _obj({"answer": _S, "rule": _S, "calculation": _S, "draft": _S, "citations": _SL, "missing": _S})


class FactIssue(BaseModel):
    claim: str
    problem: str
    correction: str


class FactCheck(BaseModel):
    verdict: str = "ok"  # ok | fix
    issues: list[FactIssue] = Field(default_factory=list)
    extra_queries: list[str] = Field(default_factory=list)

    def public(self) -> dict:
        return self.model_dump()


FACTCHECK_SCHEMA = _obj({
    "verdict": {"type": "string", "enum": ["ok", "fix"]},
    "issues": {"type": "array", "items": _obj({"claim": _S, "problem": _S, "correction": _S})},
    "extra_queries": _SL,
})


@lru_cache
def _prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


async def ask_json(prompt: str, *, system: str, schema: dict, max_tokens: int = 4000,
                   thinking_budget: int | None = None) -> tuple[dict, dict]:
    """Один JSON-запрос к подключённой модели (Gemini / Claude API / Claude Code). → (данные, usage)."""
    provider = llm_provider()
    if provider == "gemini":
        from app.services.llm import gemini

        sys = system + "\n\nВерни ТОЛЬКО JSON-объект по схеме:\n" + gemini.schema_hint(schema)
        try:
            res = await gemini.ask_json(prompt, system=sys, schema=schema, max_output_tokens=max_tokens,
                                        thinking_budget=thinking_budget)
        except gemini.GeminiError as e:
            if "INVALID_ARGUMENT" not in str(e):
                raise LawyerError(str(e)) from e
            res = await gemini.ask_json(prompt, system=sys, schema=None, max_output_tokens=max_tokens,
                                        thinking_budget=thinking_budget)
        return json.loads(_extract_json(res.text)), {**res.usage, "model": res.model}
    if provider == "claude_code":
        from app.services.llm.claude_code import ask_llm_async

        res = await ask_llm_async(prompt, system=system + JSON_INSTRUCTIONS.format(
            schema=json.dumps(schema, ensure_ascii=False)))
        return json.loads(_extract_json(res.text)), {"cost_usd": res.cost_usd, "duration_ms": res.duration_ms}
    if provider == "anthropic":
        import anthropic

        s = get_settings()
        client = anthropic.AsyncAnthropic(api_key=s.anthropic_api_key or None)
        msg = await client.messages.create(
            model=s.llm_model, max_tokens=max_tokens * 4, system=system,
            messages=[{"role": "user", "content": prompt}], thinking={"type": "adaptive"},
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}})
        if msg.stop_reason in ("refusal", "max_tokens"):
            raise LawyerError(f"stop_reason={msg.stop_reason}")
        payload = next((b.text for b in msg.content if b.type == "text"), "")
        return json.loads(payload), msg.usage.model_dump()
    raise LawyerError("языковая модель не подключена")


async def analyze_branch(question: str, kind: str, context_xml: str, raw_text: str) -> BranchAnalysis:
    prompt = (f"{context_xml}\n\n<user_message>\n{escape(raw_text)}\n</user_message>\n\n"
              f'<sub_question kind="{kind}">\n{escape(question)}\n</sub_question>')
    data, _ = await ask_json(prompt, system=_prompt("branch"), schema=BRANCH_SCHEMA,
                             max_tokens=get_settings().branch_max_output_tokens)
    return BranchAnalysis.model_validate({**data, "question": question, "kind": kind})


async def fact_check(context_xml: str, raw_text: str, answer_json: str) -> FactCheck:
    prompt = (f"{context_xml}\n\n<user_message>\n{escape(raw_text)}\n</user_message>\n\n"
              f"<answer>\n{answer_json}\n</answer>")
    data, _ = await ask_json(prompt, system=_prompt("factcheck"), schema=FACTCHECK_SCHEMA,
                             max_tokens=get_settings().factcheck_max_output_tokens)
    fc = FactCheck.model_validate(data)
    if not fc.issues:
        fc.verdict = "ok"
    return fc


def branches_block(branches: list[BranchAnalysis]) -> str:
    items = [f'<branch n="{i}" kind="{b.kind}">\n'
             f"{json.dumps(b.model_dump(exclude={'kind'}), ensure_ascii=False)}\n</branch>"
             for i, b in enumerate(branches, start=1)]
    return "<branch_analyses>\n" + "\n".join(items) + "\n</branch_analyses>"


def review_block(fc: FactCheck) -> str:
    return ("<fact_check_review>\nПроверяющий юрист нашёл ошибки в твоём предыдущем ответе. Исправь каждую, "
            "перепроверив по <context>, и верни ответ целиком заново (тот же JSON).\n"
            f"{json.dumps([i.model_dump() for i in fc.issues], ensure_ascii=False)}\n</fact_check_review>")
