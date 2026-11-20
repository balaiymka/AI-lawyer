"""Обёртка над Qdrant: коллекция `legal_chunks` с dense- и sparse-векторами.

Dev без Docker: если задан QDRANT_PATH, используется встроенный (local) режим qdrant-client
с хранением на диске. В проде — сервер Qdrant по QDRANT_URL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from qdrant_client import QdrantClient, models

from app.core.config import get_settings

COLLECTION = "legal_chunks"
DENSE = "dense"
SPARSE = "sparse"


@dataclass
class Hit:
    chunk_id: str
    score: float
    payload: dict


@lru_cache
def get_client() -> QdrantClient:
    s = get_settings()
    if s.qdrant_path:
        s.qdrant_path.mkdir(parents=True, exist_ok=True)
        return QdrantClient(path=str(s.qdrant_path))
    # 30 с вместо 5 по умолчанию: на слабом сервере (2 vCPU) запрос во время перестройки индекса идёт дольше 5 с.
    return QdrantClient(url=s.qdrant_url, timeout=30)


def ensure_collection(client: QdrantClient, dim: int = 1024) -> None:
    if client.collection_exists(COLLECTION):
        return
    client.create_collection(
        COLLECTION,
        vectors_config={DENSE: models.VectorParams(size=dim, distance=models.Distance.COSINE)},
        # Веса BGE-M3 уже обучены как лексические — IDF-модификатор не нужен.
        sparse_vectors_config={SPARSE: models.SparseVectorParams()},
    )
    for field, schema in (("act_code", "keyword"), ("lang", "keyword"), ("article", "keyword"),
                          ("is_current", "bool"), ("path", "keyword"), ("temporal", "bool"),
                          ("valid_from_i", "integer"), ("valid_to_i", "integer"), ("content_sha", "keyword"),
                          ("version_id", "keyword"), ("unit_id", "keyword"), ("point", "keyword")):
        try:
            client.create_payload_index(COLLECTION, field, field_schema=schema)
        except Exception:  # noqa: BLE001 — local mode не поддерживает payload-индексы
            pass


def upsert(client: QdrantClient, points: list[models.PointStruct]) -> None:
    for i in range(0, len(points), 128):
        client.upsert(COLLECTION, points=points[i : i + 128], wait=True)


def delete_act(client: QdrantClient, act_code: str) -> None:
    client.delete(
        COLLECTION,
        points_selector=models.FilterSelector(
            filter=models.Filter(must=[models.FieldCondition(key="act_code", match=models.MatchValue(value=act_code))])
        ),
    )


def delete_version(client: QdrantClient, version_id: str) -> None:
    client.delete(
        COLLECTION,
        points_selector=models.FilterSelector(filter=models.Filter(
            must=[models.FieldCondition(key="version_id", match=models.MatchValue(value=version_id))])),
    )


def date_int(d: date | None) -> int:
    return int(d.strftime("%Y%m%d")) if d else 99991231


def time_filter(as_of: date | None, act_dates: dict[str, date] | None = None) -> models.Filter:
    """Какая редакция участвует в поиске.

    Без даты — только действующие. С датой события: для актов с загруженной историей (`temporal`) —
    редакция, действовавшая в тот день; для остальных — действующая (истории по ним пока нет).
    """
    current = models.FieldCondition(key="is_current", match=models.MatchValue(value=True))
    if as_of is None:
        return models.Filter(must=[current])
    d = date_int(as_of)
    temporal = models.FieldCondition(key="temporal", match=models.MatchValue(value=True))

    def valid_on(day: int) -> list:
        return [models.FieldCondition(key="valid_from_i", range=models.Range(lte=day)),
                models.FieldCondition(key="valid_to_i", range=models.Range(gt=day))]

    act_dates = act_dates or {}
    should = [models.Filter(must=[current], must_not=[temporal])]
    # у каждого акта с историей — своя дата (точная редакция или ближайшая ранняя из загруженных)
    for code, day in act_dates.items():
        should.append(models.Filter(must=[temporal, models.FieldCondition(key="act_code", match=models.MatchValue(value=code)),
                                          *valid_on(date_int(day))]))
    rest = models.Filter(must=[temporal, *valid_on(d)])
    if act_dates:
        rest.must_not = [models.FieldCondition(key="act_code", match=models.MatchAny(any=list(act_dates)))]
    should.append(rest)
    return models.Filter(should=should)


def lookup_vectors(client: QdrantClient, shas: list[str]) -> dict[str, tuple[list[float], models.SparseVector]]:
    """Векторы уже посчитанных фрагментов с тем же текстом — чтобы не считать их заново для новой редакции."""
    found: dict[str, tuple[list[float], models.SparseVector]] = {}
    for i in range(0, len(shas), 256):
        flt = models.Filter(must=[models.FieldCondition(key="content_sha", match=models.MatchAny(any=shas[i:i + 256]))])
        offset = None
        while True:
            pts, offset = client.scroll(COLLECTION, scroll_filter=flt, limit=512, offset=offset,
                                        with_payload=["content_sha"], with_vectors=True)
            for p in pts:
                v = p.vector or {}
                if isinstance(v, dict) and DENSE in v and SPARSE in v:
                    found.setdefault(p.payload["content_sha"], (v[DENSE], v[SPARSE]))
            if offset is None:
                break
    return found


def _filter(langs: list[str] | None, act_codes: list[str] | None, as_of: date | None = None,
            act_dates: dict[str, date] | None = None) -> models.Filter:
    must: list = [time_filter(as_of, act_dates)]
    if langs:
        must.append(models.FieldCondition(key="lang", match=models.MatchAny(any=langs)))
    if act_codes:
        must.append(models.FieldCondition(key="act_code", match=models.MatchAny(any=act_codes)))
    return models.Filter(must=must)


def search_dense(client: QdrantClient, vector: list[float], limit: int, langs=None, act_codes=None,
                 as_of: date | None = None, act_dates: dict[str, date] | None = None) -> list[Hit]:
    res = client.query_points(COLLECTION, query=vector, using=DENSE, limit=limit,
                              query_filter=_filter(langs, act_codes, as_of, act_dates), with_payload=True)
    return [Hit(str(p.id), p.score, p.payload or {}) for p in res.points]


def search_sparse(client: QdrantClient, sparse: dict[int, float], limit: int, langs=None, act_codes=None,
                  as_of: date | None = None, act_dates: dict[str, date] | None = None) -> list[Hit]:
    if not sparse:
        return []
    vec = models.SparseVector(indices=list(sparse.keys()), values=list(sparse.values()))
    res = client.query_points(COLLECTION, query=vec, using=SPARSE, limit=limit,
                              query_filter=_filter(langs, act_codes, as_of, act_dates), with_payload=True)
    return [Hit(str(p.id), p.score, p.payload or {}) for p in res.points]
