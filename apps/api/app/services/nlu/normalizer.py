"""Нормализация запроса: шала-қазақша / ошибки / транслит → чистый запрос + поисковые формулировки.

Основной путь — Claude со строгой JSON-схемой (structured outputs). Если ключа нет или API недоступен,
работает запасной путь без LLM: определение языка по признакам + словарь сленга + извлечение ссылок.
"""

from __future__ import annotations

import json
import logging
from datetime import date
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.nlu.event_date import extract_event_date
from app.services.nlu.glossary import expand_query
from app.services.nlu.translit import is_mostly_latin, latin_to_cyrillic
from app.services.rag.refs import Ref, extract_refs
from app.services.rag.retriever import SearchRequest

log = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).parents[2] / "prompts" / "normalizer.md"


class Party(BaseModel):
    role: str
    description: str


class SearchQuery(BaseModel):
    lang: Literal["kk", "ru"]
    q: str


class NormalizedQuery(BaseModel):
    detected_lang: Literal["kk", "ru", "mixed"]
    reply_lang: Literal["kk", "ru"]
    normalized_ru: str
    normalized_kk: str
    category: str
    parties: list[Party] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    mentioned_norms: list[str] = Field(default_factory=list)
    search_queries: list[SearchQuery] = Field(default_factory=list)
    clarifying_questions: list[str] = Field(default_factory=list)
    event_date: str = ""  # ГГГГ-ММ-ДД — когда произошло событие (пусто: сейчас / неизвестно)
    event_date_precision: str = ""  # day | month | year
    source: Literal["llm", "heuristic"] = "llm"


# Схема для output_config.format — пишется явно (structured outputs поддерживают подмножество JSON Schema).
_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": _STR}
NORMALIZER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["detected_lang", "reply_lang", "normalized_ru", "normalized_kk", "category", "parties",
                 "facts", "mentioned_norms", "search_queries", "clarifying_questions", "event_date"],
    "properties": {
        "detected_lang": {"type": "string", "enum": ["kk", "ru", "mixed"]},
        "reply_lang": {"type": "string", "enum": ["kk", "ru"]},
        "normalized_ru": _STR,
        "normalized_kk": _STR,
        "category": _STR,
        "parties": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["role", "description"],
            "properties": {"role": _STR, "description": _STR}}},
        "facts": _STR_LIST,
        "mentioned_norms": _STR_LIST,
        "search_queries": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["lang", "q"],
            "properties": {"lang": {"type": "string", "enum": ["kk", "ru"]}, "q": _STR}}},
        "clarifying_questions": _STR_LIST,
        "event_date": _STR,
    },
}


class NormalizerError(RuntimeError):
    pass


@lru_cache
def _system_prompt() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


async def normalize_llm(text: str) -> NormalizedQuery:
    import anthropic

    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None)
    params = dict(
        model=settings.llm_model,
        max_tokens=4000,
        system=_system_prompt(),
        messages=[{"role": "user", "content": f"<user_message>\n{text}\n</user_message>"}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": NORMALIZER_SCHEMA}},
    )
    if settings.llm_fallbacks != "off":
        response = await client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"], fallbacks=settings.llm_fallbacks, **params
        )
    else:
        response = await client.messages.create(**params)

    if response.stop_reason == "refusal":
        raise NormalizerError(f"refusal: {getattr(response, 'stop_details', None)}")
    if response.stop_reason == "max_tokens":
        raise NormalizerError("normalizer output truncated (max_tokens)")
    payload = next((b.text for b in response.content if b.type == "text"), None)
    if payload is None:
        raise NormalizerError("no text block in normalizer response")
    nq = NormalizedQuery.model_validate({**json.loads(payload), "source": "llm"})
    return _with_event_date(nq, text)


def _with_event_date(nq: NormalizedQuery, text: str) -> NormalizedQuery:
    """Дата события: из ответа модели, иначе — по шаблонам в тексте вопроса."""
    if nq.event_date:
        try:
            date.fromisoformat(nq.event_date)
            nq.event_date_precision = nq.event_date_precision or "day"
            return nq
        except ValueError:
            nq.event_date = ""
    ev = extract_event_date(text)
    if ev:
        nq.event_date, nq.event_date_precision = ev.value.isoformat(), ev.precision
    return nq


# --- запасной путь без LLM ------------------------------------------------

KK_LETTERS = re.compile(r"[әғқңөұүһі]", re.I)
KK_WORDS = re.compile(
    r"(?<![а-яәғқңөұүһі])(жатыр|калай|қалай|бойынша|ушин|үшін|жок|жоқ|керек|истейм|істеймін|не істеу|тур|тұр|"
    r"басты|жасамай|акша|ақша|бермей|бермеди|берме|көрші|корши|пәтер|патер|үй|уй|туралы|және|деп|мен|бар|"
    r"қайда|кайда|неге|болады|ма|ме|ба|бе|па|пе)(?![а-яәғқңөұүһі])",
    re.I,
)
RU_WORDS = re.compile(
    r"(?<![а-яё])(и|в|на|что|как|по|закон[а-я]*|если|можно|нужно|сосед|квартир[а-я]*|почему|куда|делать|"
    r"подать|суд|крыша|деньги|собирает|затопил|акт)(?![а-яё])",
    re.I,
)


def detect_lang(text: str) -> tuple[str, str]:
    kk = len(KK_LETTERS.findall(text)) * 2 + len(KK_WORDS.findall(text)) * 2
    ru = len(RU_WORDS.findall(text))
    if kk and ru:
        detected = "mixed"
    elif kk:
        detected = "kk"
    else:
        detected = "ru"
    reply = "kk" if kk >= ru and kk > 0 else "ru"
    return detected, reply


def normalize_heuristic(text: str) -> NormalizedQuery:
    # Латиница («kvorum sobraniya osi») → кириллица, иначе лексический поиск и словарь сленга бессильны.
    base = latin_to_cyrillic(text) if is_mostly_latin(text) else text
    detected, reply = detect_lang(base)
    expansion = expand_query(base)
    queries = [SearchQuery(lang="ru", q=text)]
    if base != text:
        queries.append(SearchQuery(lang="ru", q=base))
    if expansion:
        # Только «запрос + термины»: отдельный запрос из одних терминов словаря уводит поиск
        # в общие статьи (напр. «оси» → статья о председателе ОСИ) — проверено на eval.
        queries.append(SearchQuery(lang="ru", q=f"{base} {expansion}"))
    nq = NormalizedQuery(
        detected_lang=detected, reply_lang=reply, normalized_ru=f"{base} {expansion}".strip(),
        normalized_kk=base, category="other", mentioned_norms=[], search_queries=queries, source="heuristic",
    )
    return _with_event_date(nq, base)


async def normalize(text: str) -> NormalizedQuery:
    # Через Claude Code нормализацию не гоняем: лишний вызов CLI = +10–20 с на каждый вопрос.
    s = get_settings()
    if s.llm_provider == "anthropic" and s.anthropic_api_key:
        try:
            return await normalize_llm(text)
        except Exception as exc:  # noqa: BLE001 — любая ошибка LLM не должна ронять поиск
            log.warning("LLM normalizer failed, falling back to heuristic: %s", exc)
    return normalize_heuristic(text)


def to_search_request(raw_text: str, nq: NormalizedQuery, top_k: int = 10) -> SearchRequest:
    queries: list[str] = []
    for q in [nq.normalized_ru, nq.normalized_kk, *[s.q for s in nq.search_queries]]:
        q = q.strip()
        if q and q not in queries:
            queries.append(q)
    refs: list[Ref] = []
    for source in [raw_text, *nq.mentioned_norms]:
        for r in extract_refs(source):
            if r not in refs:
                refs.append(r)
    rerank_query = nq.normalized_ru if nq.source == "llm" else raw_text
    as_of = date.fromisoformat(nq.event_date) if nq.event_date else None
    return SearchRequest(queries=queries[:8], rerank_query=rerank_query, refs=refs,
                         reply_lang=nq.reply_lang, top_k=top_k, as_of=as_of)
