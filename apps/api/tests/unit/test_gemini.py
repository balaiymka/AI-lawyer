"""Gemini (Vertex AI) без сети: подменяем клиента SDK."""

from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.services.lawyer import generator
from app.services.lawyer.schema import Assessment, LawyerAnswer, LegalBasis
from app.services.llm import gemini


def answer_json() -> str:
    return LawyerAnswer(
        verdict="depends", verdict_text="Зависит от обстоятельств", summary="Коротко: платят собственники.",
        legal_basis=[LegalBasis(chunk_id="ZHO:art39/p2", act="ЖЖО", article="39", point="2",
                                quote="цитата", explanation="пояснение")],
        assessment=Assessment(position="unclear", reasoning="нужно больше данных"),
        not_found=False, disclaimer="Информационный ответ.",
    ).model_dump_json()


def response(text: str, reason: str = "STOP"):
    usage = SimpleNamespace(prompt_token_count=1200, candidates_token_count=300, thoughts_token_count=50,
                            total_token_count=1550)
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=reason)],
                           usage_metadata=usage, model_version="gemini-test-flash")


class FakeModels:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    async def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def use(monkeypatch, *replies) -> FakeModels:
    models = FakeModels(replies)
    monkeypatch.setattr(gemini, "_client", lambda: SimpleNamespace(aio=SimpleNamespace(models=models)))
    return models


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_provider", "gemini")
    monkeypatch.setattr(s, "gemini_api_key", "test-gemini-key")
    monkeypatch.setattr(s, "gemini_model", "gemini-test-flash")
    monkeypatch.setattr(s, "gemini_project", "test-project")
    return s


async def collect(gen):
    return [x async for x in gen]


def test_provider_selection(settings, monkeypatch):
    assert generator.llm_provider() == "gemini"
    monkeypatch.setattr(settings, "gemini_model", "")
    assert generator.llm_provider() == "none"


async def test_ask_json_passes_limits_and_returns_usage(monkeypatch):
    models = use(monkeypatch, response('{"a": 1}'))
    res = await gemini.ask_json("q", system="sys", schema={"type": "object"}, max_output_tokens=500,
                                thinking_budget=0)
    assert res.text == '{"a": 1}' and res.model == "gemini-test-flash" and res.usage["total_token_count"] == 1550
    cfg = models.calls[0]["config"]
    assert cfg.max_output_tokens == 500 and cfg.thinking_config.thinking_budget == 0
    assert cfg.response_mime_type == "application/json" and cfg.system_instruction == "sys"


@pytest.mark.parametrize("reason,needle", [("MAX_TOKENS", "обрезан"), ("SAFETY", "отказался")])
async def test_ask_json_bad_finish_reasons(monkeypatch, reason, needle):
    use(monkeypatch, response('{"a": 1}', reason))
    with pytest.raises(gemini.GeminiError, match=needle):
        await gemini.ask_json("q", system="s")


async def test_ask_json_wraps_sdk_errors(monkeypatch):
    use(monkeypatch, RuntimeError("quota exceeded"))
    with pytest.raises(gemini.GeminiError, match="quota exceeded"):
        await gemini.ask_json("q", system="s")


async def test_generate_answer_ok(monkeypatch):
    use(monkeypatch, response(answer_json()))
    out = await collect(generator.generate_answer("вопрос"))
    final = out[-1]
    assert isinstance(final, generator.Final) and final.mode == "llm" and final.model == "gemini-test-flash"
    assert final.answer.legal_basis[0].chunk_id == "ZHO:art39/p2" and final.usage["via"] == "gemini"


async def test_generate_retries_after_invalid_json(monkeypatch):
    models = use(monkeypatch, response('{"verdict": "oops"}'), response("```json\n" + answer_json() + "\n```"))
    out = await collect(generator.generate_gemini("вопрос"))
    assert isinstance(out[-1], generator.Final)
    assert "previous_attempt_error" in models.calls[1]["contents"]


async def test_generate_retries_without_schema_when_rejected(monkeypatch):
    models = use(monkeypatch, RuntimeError("400 INVALID_ARGUMENT: bad schema"), response(answer_json()))
    out = await collect(generator.generate_gemini("вопрос"))
    assert isinstance(out[-1], generator.Final)
    assert models.calls[0]["config"].response_json_schema is not None
    assert models.calls[1]["config"].response_json_schema is None


async def test_generate_gives_up_after_two_bad_answers(monkeypatch):
    use(monkeypatch, response("не json"), response("опять не json"))
    with pytest.raises(generator.LawyerError, match="не соответствует схеме"):
        await collect(generator.generate_gemini("вопрос"))


def test_health_shows_gemini_without_key(monkeypatch):
    from app.routers.health import check_llm

    info = check_llm()
    assert info == {"provider": "gemini", "model": "gemini-test-flash", "ready": True}
    assert "test-gemini-key" not in str(info)
