"""Gemini через Vertex AI (доступ от ментора: проект eknot-zhkh-lawyer-balaiym, location global).

Ключ — только в переменной окружения GEMINI_API_KEY на сервере, не в коде и не в git.
Модель — GEMINI_MODEL (ID из Model Garden). Для разработки — Flash, старшую модель — только для финальных
проверок: лимит проекта $95 в месяц.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import get_settings


class GeminiError(RuntimeError):
    pass


@dataclass
class GeminiResult:
    text: str
    model: str
    usage: dict


def configured() -> bool:
    s = get_settings()
    return bool(s.gemini_api_key and s.gemini_model and s.gemini_project)


@lru_cache
def _client():
    from google import genai
    from google.genai import types

    s = get_settings()
    # Ключ ментора работает только с адресом вида projects/<проект>/locations/global/…: без project Vertex
    # отвечает 403 «Permission denied on resource project None».
    # Таймаут на запрос: зависший ответ Vertex не должен держать чат минутами (ветки и фактчек идут подряд).
    return genai.Client(vertexai=True, api_key=s.gemini_api_key, project=s.gemini_project or None,
                        location=s.gemini_location,
                        http_options=types.HttpOptions(timeout=s.gemini_timeout_sec * 1000))


def _usage(meta) -> dict:
    if meta is None:
        return {}
    return {k: getattr(meta, k, None) for k in
            ("prompt_token_count", "candidates_token_count", "thoughts_token_count", "total_token_count")}


async def ask_json(prompt: str, *, system: str, schema: dict | None = None, max_output_tokens: int | None = None,
                   thinking_budget: int | None = None, model: str | None = None) -> GeminiResult:
    """Один запрос, ответ — JSON-текст. Схема передаётся и в response_json_schema, и проверяется вызывающим кодом."""
    from google.genai import types

    s = get_settings()
    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_json_schema=schema,
        max_output_tokens=max_output_tokens or s.gemini_max_output_tokens,
        thinking_config=types.ThinkingConfig(
            thinking_budget=s.gemini_thinking_budget if thinking_budget is None else thinking_budget),
        temperature=0.2,
    )
    model = model or s.gemini_model
    try:
        resp = await _client().aio.models.generate_content(model=model, contents=prompt, config=config)
    except Exception as exc:  # noqa: BLE001 — сеть, лимит $95, неверный ключ: наружу понятная ошибка
        raise GeminiError(f"запрос к Gemini не удался: {type(exc).__name__}: {str(exc)[:300]}") from exc

    cand = (resp.candidates or [None])[0]
    reason = str(getattr(cand, "finish_reason", "") or "")
    if "MAX_TOKENS" in reason:
        raise GeminiError("ответ Gemini обрезан (max_output_tokens)")
    if any(r in reason for r in ("SAFETY", "BLOCKLIST", "PROHIBITED", "RECITATION")):
        raise GeminiError(f"Gemini отказался отвечать: {reason}")
    text = resp.text or ""
    if not text.strip():
        raise GeminiError(f"пустой ответ Gemini (finish_reason={reason or '—'})")
    return GeminiResult(text=text, model=getattr(resp, "model_version", None) or model, usage=_usage(resp.usage_metadata))


def schema_hint(schema: dict) -> str:
    return json.dumps(schema, ensure_ascii=False)
