"""Граф закона: разбор отсылок внутри акта и многошаговая консультация (подвопросы + фактчек) без сети."""

import json
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.services.lawyer import analysis
from app.services.lawyer import pipeline as pl
from app.services.lawyer.context import build_context
from app.services.lawyer.schema import Assessment, Calculation, Draft, LawyerAnswer
from app.services.lawyer.generator import Final
from app.services.nlu.normalizer import SubQuestion, normalize_heuristic
from app.services.rag.law_graph import GraphRef, extract_graph_refs
from app.services.rag.retriever import Result

ZHO_P8 = ("8. Собрание правомочно принимать решение, если в нем участвуют более половины от общего числа "
          "собственников квартир, нежилых помещений.\nРешение принимается при согласии большинства от общего числа "
          "собственников квартир, нежилых помещений, непосредственно принявших участие в голосовании, за исключением "
          "вопросов, указанных в подпунктах 6) –16) и 21) пункта 5 настоящей статьи, по которым решение принимается "
          "при согласии большинства от общего числа собственников квартир, нежилых помещений.")


def test_exception_with_ranges_points_to_subpoints():
    refs = extract_graph_refs(ZHO_P8, "art42/p8")
    targets = [r.target for r in refs]
    assert targets == [f"art42/p5/sp{i}" for i in range(6, 17)] + ["art42/p5/sp21"]
    assert all(r.kind == "exception" for r in refs)


@pytest.mark.parametrize("text,own,expected", [
    ("применяются правила, содержащиеся в пунктах 1 и 2 статьи 346 настоящего Кодекса.", "art348/p3",
     [GraphRef("art346/p1", "reference"), GraphRef("art346/p2", "reference")]),
    ("4. Действия, предусмотренные частью третьей настоящей статьи, совершенные", "art222/p4",
     [GraphRef("art222/p3", "reference")]),
    ("требований, установленных подпунктами 1) и 2) настоящего пункта;", "art118/p1/sp3",
     [GraphRef("art118/p1/sp1", "reference"), GraphRef("art118/p1/sp2", "reference")]),
    ("в соответствии со статьей 25 настоящего Закона.", "art10/p1", [GraphRef("art25", "reference")]),
    ("указанных в пункте 5 настоящих Правил", "p11/sp8", [GraphRef("p5", "reference")]),
    ("кроме случаев, предусмотренных пунктом 3 статьи 42 настоящего Закона", "art43/p1",
     [GraphRef("art42/p3", "exception")]),
])
def test_reference_forms(text, own, expected):
    assert extract_graph_refs(text, own) == expected


@pytest.mark.parametrize("text,own", [
    ("Для целей настоящей статьи используются понятия", "art1/p1"),  # без номера — не отсылка
    ("в соответствии с пунктом 8 настоящей статьи", "art42/p8"),  # на себя
    ("статьей 5 Закона «О связи»", "art10/p1"),  # другой акт — это xrefs.py
])
def test_not_references(text, own):
    assert extract_graph_refs(text, own) == []


# --- многошаговая консультация ------------------------------------------------------------

def res(uid, path, text):
    art, point = path.split("/")[0][3:], path.split("/")[1][1:]
    return Result(unit_id=uid, path=path, act_code="ZHO", article=art, content="", contents={"ru": f"ЗЖО › {path}\n{text}"},
                  chunk_ids={"ru": f"{uid}-ru"}, meta={"point": point, "valid_from": "2026-09-14"})


P8 = res("u8", "art42/p8", ZHO_P8)
P5_SP3 = res("u53", "art42/p5/sp3", "3) избрания председателя объединения собственников имущества;")
P5_SP7 = res("u57", "art42/p5/sp7", "7) утверждения размера текущих взносов;")


def answer(summary="Нужен кворум 51 из 100.", calcs=None):
    return LawyerAnswer(summary=summary, assessment=Assessment(position="moderate", reasoning="—"), disclaimer="—",
                        calculations=calcs or [], drafts=[Draft(title="Вопросы бюллетеня", text="1. Избрать …")])


def test_merge_interleaves_branches_without_duplicates():
    merged = pl._merge([[P5_SP3, P8], [P5_SP7, P8]])
    assert [r.unit_id for r in merged] == ["u53", "u57", "u8"]


def test_context_marks_linked_norms():
    linked = res("u8", "art42/p8", ZHO_P8)
    linked.meta.update(relation="rule_for_list", xref_from="art42/p5/sp3")
    xml, chunks = build_context([P5_SP3, linked], "ru")
    assert 'role="linked_norm"' in xml and 'linked_to="art42/p5/sp3"' in xml and "перечня" in xml
    assert chunks[1].public()["relation"] == "rule_for_list"


@pytest.fixture
def multi(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "decompose_enabled", True)
    monkeypatch.setattr(s, "factcheck_enabled", True)

    async def fake_normalize(text):
        nq = normalize_heuristic(text)
        nq.sub_questions = [SubQuestion(question="Каким большинством избирают председателя ОСИ при 100 квартирах?",
                                        kind="calculation", search_queries=["избрание председателя ОСИ"]),
                            SubQuestion(question="Каким большинством утверждают размер текущих взносов?",
                                        kind="legal", search_queries=["утверждение текущих взносов"])]
        return nq

    searched = []

    def fake_search(req):
        searched.append(req)
        hits = [P5_SP3] if "председател" in req.rerank_query else [P5_SP7] if "взнос" in req.rerank_query else [P8]
        return list(hits), SimpleNamespace(candidates=1, timings_ms={"search": 1.0})

    async def fake_graph(results, lang, limit):
        return [] if any(r.unit_id == "u8" for r in results) else [res("u8", "art42/p8", ZHO_P8)]

    calls = []

    async def fake_ask_json(prompt, *, system, schema, **kw):
        calls.append((system[:40], prompt))
        if schema is analysis.BRANCH_SCHEMA:
            return {"answer": "по общему правилу п. 8", "rule": "большинство участников", "calculation": "51 → 26",
                    "draft": "", "citations": ["u8-ru"], "missing": ""}, {}
        fix = sum(1 for c in calls if c[0].startswith("Ты — проверяющий")) == 1
        return ({"verdict": "fix", "issues": [{"claim": "взносы — большинство участников", "problem": "пп. 7) в исключении п. 8",
                                               "correction": "большинство от общего числа: 51 из 100"}],
                 "extra_queries": ["кворум собрания"]} if fix else {"verdict": "ok", "issues": [], "extra_queries": []}), {}

    generations = []

    def fake_generate(content):
        generations.append(content)

        async def gen():
            calc = [Calculation(item="взносы", rule="большинство от общего числа", result="51 из 100", citations=["u8-ru", "bad"])]
            yield Final(answer(calcs=calc), "llm", "fake", {})
        return gen()

    monkeypatch.setattr(pl, "normalize", fake_normalize)
    monkeypatch.setattr(pl, "search", fake_search)
    monkeypatch.setattr(pl, "expand_with_graph", fake_graph)
    monkeypatch.setattr(pl, "llm_available", lambda: True)
    monkeypatch.setattr(pl, "generate_answer", fake_generate)
    monkeypatch.setattr(analysis, "ask_json", fake_ask_json)
    return SimpleNamespace(searched=searched, calls=calls, generations=generations)


async def test_pipeline_branches_factcheck_and_revision(multi):
    events = [e async for e in pl.run_chat("100 квартир: председатель и тариф, какой кворум?", persist=False)]
    stages = [e.data["stage"] for e in events if e.name == "status"]
    assert stages == ["normalize", "search", "answer", "factcheck"]

    # каждый подвопрос — свой поиск с собственной формулировкой для реранкера, плюс поиск по замечанию фактчека
    assert [r.rerank_query for r in multi.searched][:2] == [
        "Каким большинством избирают председателя ОСИ при 100 квартирах?",
        "Каким большинством утверждают размер текущих взносов?"]
    assert multi.searched[2].queries == ["кворум собрания"]

    # итоговый ответ видит разборы веток; переработка — замечания фактчека
    assert "<branch_analyses>" in multi.generations[0] and "<fact_check_review>" not in multi.generations[0]
    assert "<fact_check_review>" in multi.generations[1] and "51 из 100" in multi.generations[1]

    ans = next(e for e in events if e.name == "answer").data
    fc = ans["analysis"]["fact_check"]
    assert fc["verdict"] == "fix" and fc["revised"] is True
    assert len(ans["analysis"]["branches"]) == 2 and len(ans["analysis"]["sub_questions"]) == 2
    assert ans["answer"]["calculations"][0]["citations"] == ["u8-ru"]  # выдуманный chunk_id убран
    assert ans["answer"]["drafts"][0]["title"] == "Вопросы бюллетеня"


async def test_single_question_skips_branches(multi, monkeypatch):
    async def one(text):
        nq = normalize_heuristic(text)
        nq.sub_questions = [SubQuestion(question="кворум", kind="legal")]
        return nq

    monkeypatch.setattr(pl, "normalize", one)
    events = [e async for e in pl.run_chat("какой кворум собрания", persist=False)]
    ans = next(e for e in events if e.name == "answer").data
    assert ans["analysis"]["branches"] == [] and "<branch_analyses>" not in multi.generations[0]


async def test_factcheck_failure_keeps_answer(multi, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("quota")

    monkeypatch.setattr(pl, "fact_check", boom)
    events = [e async for e in pl.run_chat("100 квартир: председатель и тариф", persist=False)]
    ans = next(e for e in events if e.name == "answer").data
    assert ans["analysis"]["fact_check"]["verdict"] == "error" and ans["answer"]["summary"]


def test_branches_block_is_json():
    b = analysis.BranchAnalysis(question="q", kind="calculation", answer="a", citations=["c1"])
    block = analysis.branches_block([b])
    payload = block.split("\n")[2]
    assert json.loads(payload)["citations"] == ["c1"] and 'kind="calculation"' in block
