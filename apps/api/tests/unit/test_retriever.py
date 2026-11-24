"""Логика гибридного поиска на подставных моделях и Qdrant в памяти (без скачивания весов)."""

import uuid

import pytest
from qdrant_client import QdrantClient, models

from app.services.rag import retriever as rt
from app.services.rag import vector_store as vs
from app.services.rag.models import Encoded
from app.services.rag.refs import Ref

VOCAB = ["кворум", "собрание", "голос", "затопление", "ущерб", "протокол", "копия", "взнос"]


def fake_encode(text: str) -> Encoded:
    t = text.lower()
    dense = [1.0 if w in t else 0.0 for w in VOCAB]
    if not any(dense):
        dense[0] = 0.01
    sparse = {i + 1: 1.0 for i, w in enumerate(VOCAB) if w in t}
    return Encoded(dense=dense, sparse=sparse)


class FakeEmbedder:
    def encode(self, texts, max_length=256, batch_size=8):
        return [fake_encode(t) for t in texts]


class FakeReranker:
    """Оценка = доля слов запроса в тексте — достаточно, чтобы проверить переупорядочивание."""

    def score(self, query, passages, max_length=512, batch_size=8):
        words = [w for w in VOCAB if w in query.lower()]
        return [sum(w in p.lower() for w in words) / max(len(words), 1) for p in passages]


UNITS = [
    ("art42/p8", "42", "8", "ru", "Собрание правомочно, кворум более половины собственников"),
    ("art42/p8", "42", "8", "kk", "Жиналыс кворум жартысынан көбі"),
    ("art42/p7", "42", "7", "ru", "Собственник имеет один голос на собрание"),
    ("art42/p17", "42", "17", "ru", "Копия протокола собрание выдается за пять рабочих дней"),
    ("art39/p1", "39", "1", "ru", "Затопление: ущерб возмещает собственник"),
    ("art34-1/p1", "34-1", "1", "ru", "Собственники обязаны платить взнос"),
]


@pytest.fixture
def store(monkeypatch):
    from app.core.config import get_settings

    # Тесты проверяют логику с реранкером независимо от локального .env (RERANK_ENABLED=false).
    monkeypatch.setattr(get_settings(), "rerank_enabled", True)
    client = QdrantClient(":memory:")
    client.create_collection(
        vs.COLLECTION,
        vectors_config={vs.DENSE: models.VectorParams(size=len(VOCAB), distance=models.Distance.COSINE)},
        sparse_vectors_config={vs.SPARSE: models.SparseVectorParams()},
    )
    unit_ids = {}
    points = []
    for path, art, point, lang, text in UNITS:
        uid = unit_ids.setdefault(path, str(uuid.uuid4()))
        enc = fake_encode(text)
        points.append(models.PointStruct(
            id=str(uuid.uuid4()),
            vector={vs.DENSE: enc.dense, vs.SPARSE: models.SparseVector(indices=list(enc.sparse), values=list(enc.sparse.values()))},
            payload={"unit_id": uid, "path": path, "act_code": "ZHO", "article": art, "point": point,
                     "lang": lang, "content": text, "is_current": True},
        ))
    client.upsert(vs.COLLECTION, points)
    monkeypatch.setattr(vs, "get_client", lambda: client)
    monkeypatch.setattr(rt, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(rt, "get_reranker", lambda: FakeReranker())
    return client


def test_hybrid_search_ranks_relevant_point_first(store):
    req = rt.SearchRequest(queries=["кворум собрание"], rerank_query="кворум собрание", top_k=3)
    results, trace = rt.search(req)
    assert results[0].path == "art42/p8"
    assert set(results[0].contents) == {"ru", "kk"}  # два языка — одна единица
    assert results[0].content.startswith("Собрание правомочно")  # язык ответа ru
    assert {"dense", "sparse"} <= set(results[0].channels)
    assert "rerank" in trace.timings_ms


def test_reply_language_picks_kazakh_text(store):
    req = rt.SearchRequest(queries=["кворум"], rerank_query="кворум", reply_lang="kk", top_k=1)
    results, _ = rt.search(req)
    assert results[0].content.startswith("Жиналыс")


def test_explicit_reference_is_pinned_even_if_semantically_far(store):
    # Запрос про затопление, но пользователь явно назвал ст. 42 п. 17 — пункт обязан попасть в выдачу.
    req = rt.SearchRequest(queries=["затопление ущерб"], rerank_query="затопление ущерб",
                           refs=[Ref("42", "17")], top_k=2)
    results, _ = rt.search(req)
    paths = [r.path for r in results]
    assert paths[0] == "art39/p1"
    assert "art42/p17" in paths
    assert next(r for r in results if r.path == "art42/p17").pinned


def test_missing_point_falls_back_to_whole_article(store):
    req = rt.SearchRequest(queries=["взнос"], rerank_query="взнос", refs=[Ref("42", "99")], top_k=10,
                           use_reranker=False)
    results, _ = rt.search(req)
    pinned = {r.path for r in results if r.pinned}
    assert pinned == {"art42/p7", "art42/p8", "art42/p17"}


def test_core_housing_act_gets_rerank_slot(store, monkeypatch):
    """Большой кодекс заполняет голову RRF, но пункт ЗЖО всё равно доходит до реранкера и выигрывает."""
    from app.core.config import get_settings

    points = []
    for i in range(4):
        enc = fake_encode("ущерб")
        points.append(models.PointStruct(
            id=str(uuid.uuid4()),
            vector={vs.DENSE: enc.dense, vs.SPARSE: models.SparseVector(indices=list(enc.sparse), values=list(enc.sparse.values()))},
            payload={"unit_id": str(uuid.uuid4()), "path": f"art{500 + i}/p1", "act_code": "KOAP", "article": str(500 + i),
                     "point": "1", "lang": "ru", "content": "ущерб", "is_current": True}))
    store.upsert(vs.COLLECTION, points)
    # «ущерб взнос копия протокол» дальше от поискового запроса «ущерб», но точнее отвечает на вопрос
    enc = fake_encode("ущерб взнос копия протокол")
    store.upsert(vs.COLLECTION, [models.PointStruct(
        id=str(uuid.uuid4()),
        vector={vs.DENSE: enc.dense, vs.SPARSE: models.SparseVector(indices=list(enc.sparse), values=list(enc.sparse.values()))},
        payload={"unit_id": str(uuid.uuid4()), "path": "art34/p7", "act_code": "ZHO", "article": "34", "point": "7",
                 "lang": "ru", "content": "ущерб взнос копия протокол", "is_current": True})])
    req = rt.SearchRequest(queries=["ущерб"], rerank_query="ущерб взнос", top_k=2, rerank_pool=2, xref_limit=0)

    monkeypatch.setattr(get_settings(), "core_rerank_extra", 0)
    assert "art34/p7" not in [r.path for r in rt.search(req)[0]]
    monkeypatch.setattr(get_settings(), "core_rerank_extra", 4)
    assert rt.search(req)[0][0].path == "art34/p7"
