"""Генерация ответа AI-юриста.

* Claude (`settings.llm_model`) — адаптивное мышление, effort high, structured output по LAWYER_SCHEMA,
  стриминг, server-side fallbacks при отказе модели, кэширование системного промпта.
* Gemini через Vertex AI (`LLM_PROVIDER=gemini`) — JSON по той же схеме, проверка и одна повторная попытка.
* Демо-режим (нет ключа) — честный ответ без толкования: показывает найденные нормы
  дословно, ничего не придумывает. Нужен, чтобы интерфейс и проверка ссылок работали без ключа.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.services.lawyer.context import ContextChunk
from app.services.lawyer.schema import AVAILABLE_TEMPLATES, LAWYER_SCHEMA, Assessment, LawyerAnswer, LegalBasis
from app.services.lawyer.verify import _excerpt

log = logging.getLogger(__name__)
PROMPT_FILE = Path(__file__).parents[2] / "prompts" / "lawyer.md"


class LawyerError(RuntimeError):
    pass


@dataclass
class Delta:
    text: str


@dataclass
class Final:
    answer: LawyerAnswer
    mode: str  # llm | demo
    model: str | None = None
    usage: dict | None = None


@lru_cache
def _system_prompt() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


ROLE_LABELS = {"owner": "собственник квартиры", "osi": "председатель / член совета ОСИ или ПТ",
               "uk": "управляющая компания", "lawyer": "практикующий юрист"}


def build_user_content(context_xml: str, normalized: dict, raw_text: str, role: str | None,
                       history: list[dict] | None = None) -> str:
    event = normalized.get("event_date") or ""
    precision = normalized.get("event_date_precision") or ""
    templates = "\n".join(f'<template code="{k}">{v}</template>' for k, v in AVAILABLE_TEMPLATES.items())
    parts = [f"<available_templates>\n{templates}\n</available_templates>", context_xml,
             f"<normalized>{json.dumps(normalized, ensure_ascii=False)}</normalized>"]
    parts.append(f'<event_date precision="{precision}">{event}</event_date>')
    for ed in normalized.get("editions") or []:
        if not ed.get("exact"):
            parts.append(f"<edition_note>На дату события в базе нет точной редакции {ed['act_code']}: применена "
                         f"ближайшая более ранняя (с {ed['valid_from']} по {ed.get('valid_to') or '…'}). Скажи об этом в "
                         f"legal_answer и посоветуй сверить норму с редакцией на дату события на adilet.zan.kz."
                         f"</edition_note>")
    if role:
        parts.append(f"<user_role>{ROLE_LABELS.get(role, role)}</user_role>")
    if history:
        prev = "\n".join(f"<{m['role']}>{m['text']}</{m['role']}>" for m in history[-6:])
        parts.append(f"<previous_turns>\n{prev}\n</previous_turns>")
    parts.append(f"<user_message>\n{raw_text}\n</user_message>")
    return "\n\n".join(parts)


async def generate_llm(user_content: str) -> AsyncIterator[Delta | Final]:
    import anthropic

    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None)
    params = dict(
        model=settings.llm_model,
        max_tokens=64000,
        system=[{"type": "text", "text": _system_prompt(), "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_content}],
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": LAWYER_SCHEMA}},
    )
    if settings.llm_fallbacks != "off":
        stream_cm = client.beta.messages.stream(
            betas=["server-side-fallback-2026-07-01"], fallbacks=settings.llm_fallbacks, **params)
    else:
        stream_cm = client.messages.stream(**params)

    async with stream_cm as stream:
        async for text in stream.text_stream:
            yield Delta(text)
        message = await stream.get_final_message()

    if message.stop_reason == "refusal":
        raise LawyerError(f"refusal: {getattr(message, 'stop_details', None)}")
    if message.stop_reason == "max_tokens":
        raise LawyerError("answer truncated (max_tokens)")
    payload = next((b.text for b in message.content if b.type == "text"), None)
    if payload is None:
        raise LawyerError("no text block in answer")
    usage = message.usage.model_dump() if getattr(message, "usage", None) else None
    yield Final(LawyerAnswer.model_validate_json(payload), "llm", getattr(message, "model", settings.llm_model), usage)


DEMO_TEXT = {
    "ru": {
        "verdict": "Без AI-юриста оценить, правы ли вы, нельзя — ниже нормы, которые относятся к вопросу.",
        "summary": "Демо-режим: AI-юрист ещё не подключён, поэтому толкования нет. Ниже — пункты закона, "
                   "которые поиск счёл самыми близкими к вашему вопросу. Прочитайте их дословно.",
        "none": "В базе портала не найдена норма, прямо регулирующая этот вопрос. Попробуйте описать ситуацию "
                "подробнее: кто участвует, что произошло, что вы хотите получить.",
        "explanation": "Найдено поиском. Объяснение, как норма применяется к вашей ситуации, появится после "
                       "подключения AI-юриста.",
        "reasoning": "Оценка позиции требует анализа AI-юриста.",
        "disclaimer": "Ответ носит информационный характер и основан на текстах НПА с adilet.zan.kz; "
                      "для представительства в суде рекомендуется адвокат или юрист.",
    },
    "kk": {
        "verdict": "AI-заңгерсіз сіздің құқығыңызды бағалау мүмкін емес — төменде сұраққа қатысты нормалар.",
        "summary": "Демо-режим: AI-заңгер әлі қосылмаған, сондықтан түсіндірме жоқ. Төменде іздеу жүйесі "
                   "сұрағыңызға ең жақын деп тапқан заң тармақтары берілген. Оларды сөзбе-сөз оқыңыз.",
        "none": "Портал базасынан бұл мәселені тікелей реттейтін норма табылмады. Жағдайды толығырақ "
                "сипаттаңыз: кім қатысады, не болды, нені алғыңыз келеді.",
        "explanation": "Іздеу арқылы табылды. Норманың сіздің жағдайыңызға қалай қолданылатыны AI-заңгер "
                       "қосылғаннан кейін түсіндіріледі.",
        "reasoning": "Позицияны бағалау үшін AI-заңгердің талдауы қажет.",
        "disclaimer": "Жауап ақпараттық сипатта және adilet.zan.kz сайтындағы НҚА мәтіндеріне негізделген; "
                      "сотта өкілдік ету үшін адвокатқа немесе заңгерге жүгінген жөн.",
    },
}


async def generate_demo(chunks: list[ContextChunk], reply_lang: str, top: int = 3) -> AsyncIterator[Delta | Final]:
    t = DEMO_TEXT.get(reply_lang, DEMO_TEXT["ru"])
    picked = chunks[:top]
    answer = LawyerAnswer(
        verdict="depends",
        verdict_text=t["verdict"],
        summary=t["summary"] if picked else t["none"],
        legal_basis=[LegalBasis(chunk_id=c.chunk_id, act=c.act_title, article=c.article or "", point=c.point or "",
                                quote=_excerpt(c.text), explanation=t["explanation"]) for c in picked],
        assessment=Assessment(position="unclear", reasoning=t["reasoning"]),
        not_found=not picked,
        disclaimer=t["disclaimer"],
    )
    # Имитируем поток, чтобы интерфейс вёл себя так же, как с моделью.
    for word in answer.summary.split(" "):
        yield Delta(word + " ")
        await asyncio.sleep(0.02)
    yield Final(answer, "demo")


# --- Claude Code (подписка) -------------------------------------------------------------

JSON_INSTRUCTIONS = """
<response_format>
Верни ТОЛЬКО один JSON-объект, строго соответствующий схеме ниже: без пояснений до или после,
без markdown и без ```. Все поля обязательны (пустые списки — []). chunk_id и citations — только из <context>.
<schema>
{schema}
</schema>
</response_format>"""


def _extract_json(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        raise LawyerError("в ответе нет JSON-объекта")
    return t[start:end + 1]


async def generate_claude_code(user_content: str) -> AsyncIterator[Delta | Final]:
    """Ответ юриста через локальный `claude -p` (подписка). Без стриминга: ответ приходит целиком."""
    from pydantic import ValidationError

    from app.services.llm.claude_code import ask_llm_async

    system = _system_prompt() + JSON_INSTRUCTIONS.format(schema=json.dumps(LAWYER_SCHEMA, ensure_ascii=False))
    prompt = user_content
    for attempt in range(2):  # одна повторная попытка, если JSON не прошёл проверку схемы
        res = await ask_llm_async(prompt, system=system)
        try:
            answer = LawyerAnswer.model_validate_json(_extract_json(res.text))
        except (ValidationError, LawyerError, ValueError) as e:
            if attempt == 1:
                raise LawyerError(f"ответ claude не соответствует схеме: {str(e)[:300]}") from e
            prompt = (user_content + "\n\n<previous_attempt_error>Предыдущий ответ не прошёл проверку схемы: "
                      f"{str(e)[:500]}. Верни исправленный JSON целиком.</previous_attempt_error>")
            continue
        yield Delta(answer.summary)
        usage = {"cost_usd": res.cost_usd, "duration_ms": res.duration_ms, "via": "claude_code"}
        yield Final(answer, "llm", get_settings().claude_model or "claude-code", usage)
        return


# --- Gemini (Vertex AI) -------------------------------------------------------------------

async def generate_gemini(user_content: str) -> AsyncIterator[Delta | Final]:
    """Ответ юриста через Gemini. JSON по LAWYER_SCHEMA, проверка pydantic, одна повторная попытка."""
    from pydantic import ValidationError

    from app.services.llm import gemini

    system = _system_prompt() + JSON_INSTRUCTIONS.format(schema=gemini.schema_hint(LAWYER_SCHEMA))
    prompt, schema = user_content, LAWYER_SCHEMA
    for attempt in range(2):
        try:
            res = await gemini.ask_json(prompt, system=system, schema=schema)
        except gemini.GeminiError as e:
            # Vertex принимает не все конструкции JSON Schema — тогда просим JSON только инструкцией в промпте.
            if attempt == 0 and schema is not None and "INVALID_ARGUMENT" in str(e):
                log.warning("Gemini rejected response schema, retrying without it: %s", e)
                schema = None
                continue
            raise LawyerError(str(e)) from e
        try:
            answer = LawyerAnswer.model_validate_json(_extract_json(res.text))
        except (ValidationError, LawyerError, ValueError) as e:
            if attempt == 1:
                raise LawyerError(f"ответ Gemini не соответствует схеме: {str(e)[:300]}") from e
            prompt = (user_content + "\n\n<previous_attempt_error>Предыдущий ответ не прошёл проверку схемы: "
                      f"{str(e)[:500]}. Верни исправленный JSON целиком.</previous_attempt_error>")
            continue
        yield Delta(answer.summary)
        yield Final(answer, "llm", res.model, {**res.usage, "via": "gemini"})
        return
    raise LawyerError("Gemini не вернул корректный ответ")


def llm_provider() -> str:
    """Какой LLM реально доступен: anthropic | gemini | claude_code | none."""
    s = get_settings()
    if s.llm_provider == "gemini":
        from app.services.llm import gemini

        return "gemini" if gemini.configured() else "none"
    if s.llm_provider == "claude_code":
        from app.services.llm.claude_code import find_claude

        return "claude_code" if find_claude() else "none"
    if s.llm_provider == "anthropic" and s.anthropic_api_key:
        return "anthropic"
    return "none"


def llm_available() -> bool:
    return llm_provider() != "none"


def generate_answer(user_content: str) -> AsyncIterator[Delta | Final]:
    provider = llm_provider()
    if provider == "gemini":
        return generate_gemini(user_content)
    return generate_claude_code(user_content) if provider == "claude_code" else generate_llm(user_content)
