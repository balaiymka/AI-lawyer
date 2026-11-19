import json
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.services.nlu import normalizer as nz


@pytest.mark.parametrize(
    ("text", "detected", "reply"),
    [
        ("Сосед сверху затопил квартиру, что делать?", "ru", "ru"),
        ("Көрші пәтерді су басты, не істеу керек?", "kk", "kk"),
        ("кск акша жинап жатыр но крыша тесилып тур не истейм по закону", "mixed", "kk"),
        ("сосед сверху затопил акт жасамай жатыр ОСИ калай подать в суд", "mixed", "kk"),
    ],
)
def test_detect_lang(text, detected, reply):
    assert nz.detect_lang(text) == (detected, reply)


def test_heuristic_expands_slang_and_extracts_refs():
    text = "оси протокол бермей жатыр 42 бап 17 тармак"
    nq = nz.normalize_heuristic(text)
    assert nq.source == "heuristic"
    joined = " ".join(q.q for q in nq.search_queries)
    assert "объединение собственников имущества" in joined
    assert "копия протокола" in joined
    req = nz.to_search_request(text, nq)
    assert [(r.article, r.point) for r in req.refs] == [("42", "17")]
    assert req.reply_lang == "kk"


LLM_JSON = {
    "detected_lang": "mixed", "reply_lang": "kk",
    "normalized_ru": "ОСИ не выдаёт копию протокола собрания", "normalized_kk": "МИБ хаттама көшірмесін бермейді",
    "category": "osi_governance", "parties": [{"role": "osi", "description": "ОСИ"}], "facts": [],
    "mentioned_norms": ["ст. 42 п. 17"],
    "search_queries": [{"lang": "ru", "q": "копия протокола собрания по требованию собственника срок"}],
    "clarifying_questions": [],
}


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _fake_client(monkeypatch, response):
    messages = FakeMessages(response)
    client = SimpleNamespace(messages=messages, beta=SimpleNamespace(messages=messages))
    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", lambda **_: client)
    return messages


async def test_llm_normalizer_parses_structured_output(monkeypatch):
    resp = SimpleNamespace(stop_reason="end_turn",
                           content=[SimpleNamespace(type="text", text=json.dumps(LLM_JSON, ensure_ascii=False))])
    messages = _fake_client(monkeypatch, resp)
    nq = await nz.normalize_llm("оси протокол бермей жатыр")
    assert nq.reply_lang == "kk" and nq.source == "llm"
    call = messages.calls[0]
    assert call["model"] == get_settings().llm_model
    assert call["output_config"]["format"]["schema"] is nz.NORMALIZER_SCHEMA
    assert call["output_config"]["effort"] == "low"
    assert "<user_message>" in call["messages"][0]["content"]
    req = nz.to_search_request("оси протокол бермей жатыр", nq)
    assert req.rerank_query == "ОСИ не выдаёт копию протокола собрания"
    assert [(r.article, r.point) for r in req.refs] == [("42", "17")]


async def test_refusal_falls_back_to_heuristic(monkeypatch):
    resp = SimpleNamespace(stop_reason="refusal", stop_details=None, content=[])
    _fake_client(monkeypatch, resp)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    nq = await nz.normalize("сосед затопил")
    assert nq.source == "heuristic"
