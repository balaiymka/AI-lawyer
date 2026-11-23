"""AI-юрист: контекст, проверка ссылок, демо-режим, поток Claude (подставной клиент), конвейер чата."""

import json
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.services.lawyer import generator as gen
from app.services.lawyer import pipeline as pl
from app.services.lawyer.context import build_context
from app.services.lawyer.schema import Assessment, LawyerAnswer, LegalBasis, ActionStep
from app.services.lawyer.verify import verify_answer
from app.services.nlu.normalizer import normalize_heuristic
from app.services.rag.retriever import Result

P17_RU = ("Закон РК «О жилищных отношениях» › Статья 42 › п. 17\n"
          "Копия протокола собрания предоставляется собственнику по письменному запросу "
          "в течение пяти рабочих дней.")
P17_KK = "42-бап › 17-тармақ\nЖиналыс хаттамасының көшірмесі жазбаша сұрау бойынша бес жұмыс күні ішінде беріледі."
P8_RU = "Статья 42 › п. 8\nСобрание правомочно, если в нём участвуют более половины собственников."


def result(uid, art, point, contents):
    return Result(unit_id=uid, path=f"art{art}/p{point}", act_code="ZHO", article=art, content="",
                  contents=contents, chunk_ids={lang: f"{uid}-{lang}" for lang in contents},
                  meta={"point": point, "valid_from": "2024-01-01", "breadcrumb_ru": "ЗЖО › Статья 42"})


@pytest.fixture
def chunks():
    rs = [result("u17", "42", "17", {"ru": P17_RU, "kk": P17_KK}), result("u8", "42", "8", {"ru": P8_RU})]
    xml, cs = build_context(rs, "ru")
    return xml, cs


def make_answer(**kw):
    base = dict(summary="Копию протокола выдают за 5 рабочих дней (ст. 42 п. 17).",
                assessment=Assessment(position="strong", reasoning="Норма прямая."), disclaimer="—")
    return LawyerAnswer(**{**base, **kw})


def test_context_has_attributes_and_url(chunks):
    xml, cs = chunks
    assert 'chunk_id="u17-ru"' in xml and 'article="42"' in xml and 'point="17"' in xml
    assert "adilet.zan.kz/rus/docs/Z970000094_" in xml
    assert cs[0].text.startswith("Копия протокола")  # строка «хлебных крошек» отрезана
    assert cs[0].act_title.startswith("Закон Республики Казахстан")


def test_verify_keeps_exact_quote_and_fixes_metadata(chunks):
    _, cs = chunks
    a = make_answer(legal_basis=[LegalBasis(chunk_id="u17-ru", act="что-то", article="99", point="1",
                                            quote="«копия протокола  собрания предоставляется собственнику»",
                                            explanation="…")])
    a, v = verify_answer(a, cs)
    b = a.legal_basis[0]
    assert (b.article, b.point, b.quote_verified) == ("42", "17", True)
    assert b.act.startswith("Закон")
    assert not v.needs_review


def test_verify_accepts_quote_in_other_language_and_ellipsis(chunks):
    _, cs = chunks
    a = make_answer(legal_basis=[
        LegalBasis(chunk_id="u17-ru", act="", article="42", point="17",
                   quote="Жиналыс хаттамасының көшірмесі … бес жұмыс күні ішінде беріледі", explanation="")])
    a, v = verify_answer(a, cs)
    assert a.legal_basis[0].quote_verified and v.replaced_quotes == 0


def test_verify_replaces_invented_quote(chunks):
    _, cs = chunks
    a = make_answer(legal_basis=[LegalBasis(chunk_id="u8-ru", act="", article="42", point="8",
                                            quote="Собрание правомочно при участии двух третей собственников",
                                            explanation="")])
    a, v = verify_answer(a, cs)
    assert a.legal_basis[0].quote_verified is False
    assert a.legal_basis[0].quote.startswith("Собрание правомочно, если в нём участвуют более половины")
    assert v.replaced_quotes == 1 and v.needs_review


def test_verify_drops_unknown_chunks_and_flags_free_text_refs(chunks):
    _, cs = chunks
    a = make_answer(
        summary="Согласно статье 917 ГК сосед отвечает, а по ст. 42 п. 17 — ОСИ.",
        legal_basis=[
            LegalBasis(chunk_id="made-up", act="ГК", article="917", point="1", quote="Вред возмещается", explanation=""),
            LegalBasis(chunk_id="wrong-id", act="", article="42", point="8", quote="более половины собственников",
                       explanation=""),  # неизвестный id, но такой пункт есть в контексте → привязываем
        ],
        action_plan=[ActionStep(step="Запрос", who="Вы", where="ОСИ", deadline="5 дней",
                                citations=["u17-ru", "ghost"])],
    )
    a, v = verify_answer(a, cs)
    assert [b.chunk_id for b in a.legal_basis] == ["u8-ru"]
    assert a.action_plan[0].citations == ["u17-ru"]
    assert set(v.removed_citations) == {"made-up", "ghost"}
    assert v.unverified_refs == ["917"]


async def test_demo_answer_quotes_found_norms_only(chunks):
    _, cs = chunks
    items = [x async for x in gen.generate_demo(cs, "kk")]
    final = items[-1]
    assert isinstance(final, gen.Final) and final.mode == "demo"
    assert any(isinstance(x, gen.Delta) for x in items[:-1])
    assert [b.chunk_id for b in final.answer.legal_basis] == ["u17-ru", "u8-ru"]
    assert final.answer.summary.startswith("Демо-режим: AI-заңгер")
    empty = [x async for x in gen.generate_demo([], "ru")][-1]
    assert empty.answer.not_found and empty.answer.legal_basis == []


ANSWER_JSON = make_answer(legal_basis=[LegalBasis(
    chunk_id="u17-ru", act="", article="42", point="17",
    quote="Копия протокола собрания предоставляется собственнику по письменному запросу",
    explanation="Срок — 5 рабочих дней.")], documents=["protocol_copy_request"]).model_dump(exclude={"legal_basis": {0: {"quote_verified"}}})


class FakeStream:
    def __init__(self, payload, stop_reason="end_turn"):
        self.payload, self.stop_reason = payload, stop_reason

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    @property
    def text_stream(self):
        async def it():
            for i in range(0, len(self.payload), 50):
                yield self.payload[i:i + 50]
        return it()

    async def get_final_message(self):
        return SimpleNamespace(stop_reason=self.stop_reason, model="claude-opus-5-5",
                               content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=self.payload)],
                               usage=None)


def fake_client(captured, payload, stop_reason="end_turn"):
    class Messages:
        def stream(self, **kw):
            captured.update(kw)
            return FakeStream(payload, stop_reason)

    class Client:
        def __init__(self, **_):
            self.beta = SimpleNamespace(messages=Messages())
            self.messages = Messages()

    return Client


async def test_llm_stream_request_shape(monkeypatch):
    import anthropic

    captured = {}
    monkeypatch.setattr(anthropic, "AsyncAnthropic", fake_client(captured, json.dumps(ANSWER_JSON, ensure_ascii=False)))
    items = [x async for x in gen.generate_llm("<context/>")]
    assert "".join(x.text for x in items if isinstance(x, gen.Delta)) == json.dumps(ANSWER_JSON, ensure_ascii=False)
    final = items[-1]
    assert final.mode == "llm" and final.answer.documents == ["protocol_copy_request"]
    assert captured["model"] == get_settings().llm_model
    assert captured["thinking"] == {"type": "adaptive"}
    assert captured["output_config"]["effort"] == "high"
    assert captured["output_config"]["format"]["type"] == "json_schema"
    assert captured["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert captured["betas"] == ["server-side-fallback-2026-07-01"]


async def test_llm_refusal_raises(monkeypatch):
    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", fake_client({}, "{}", stop_reason="refusal"))
    with pytest.raises(gen.LawyerError):
        [x async for x in gen.generate_llm("x")]


async def test_pipeline_events_demo_mode(monkeypatch, chunks):
    rs = [result("u17", "42", "17", {"ru": P17_RU, "kk": P17_KK})]

    async def fake_normalize(text):
        return normalize_heuristic(text)

    monkeypatch.setattr(pl, "normalize", fake_normalize)
    monkeypatch.setattr(pl, "search", lambda req: (rs, SimpleNamespace(candidates=1, timings_ms={})))
    monkeypatch.setattr(pl, "llm_available", lambda: False)

    async def no_graph(*a):
        return []

    monkeypatch.setattr(pl, "expand_with_graph", no_graph)
    events = [e async for e in pl.run_chat("ОСИ не даёт копию протокола", persist=False)]
    names = [e.name for e in events]
    assert names[0] == "status" and names[-1] == "done"
    assert {"normalized", "sources", "delta", "answer"} <= set(names)
    ans = next(e for e in events if e.name == "answer").data
    assert ans["mode"] == "demo" and ans["verification"]["needs_review"] is False
    assert ans["answer"]["legal_basis"][0]["article"] == "42"


def test_user_content_order():
    s = gen.build_user_content("<context></context>", {"reply_lang": "ru"}, "вопрос", "owner",
                               [{"role": "user", "text": "раньше"}])
    order = [s.index(t) for t in ("<available_templates>", "<context>", "<normalized>", "<user_role>",
                                  "<previous_turns>", "<user_message>")]
    assert order == sorted(order)
