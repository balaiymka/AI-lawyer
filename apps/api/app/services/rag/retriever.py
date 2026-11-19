"""Гибридный поиск по нормам: точные ссылки + dense + sparse → RRF → реранкер.

Вход — SearchRequest: несколько поисковых формулировок (от нормализатора или запасного режима),
формулировка для реранкера, распознанные ссылки на статьи.
Выход — список единиц (пунктов/статей), лучший первым, с текстом на нужном языке.
"""

from __future__ import annotations

import time
from collections import Counter
from functools import lru_cache
from dataclasses import dataclass, field
from datetime import date

from qdrant_client import models

from app.core.config import get_settings
from app.services.rag import vector_store as vs
from app.services.rag.models import get_embedder, get_reranker
from app.services.rag.refs import Ref
from app.services.rag.xrefs import XRef, extract_xrefs

RRF_K = 60
EXACT_WEIGHT = 2.0


@dataclass
class SearchRequest:
    queries: list[str]
    rerank_query: str
    refs: list[Ref] = field(default_factory=list)
    reply_lang: str = "ru"
    act_codes: list[str] | None = None
    top_k: int = 10
    per_channel: int = 30
    rerank_pool: int | None = None  # None — из настроек
    use_reranker: bool | None = None  # None — из настроек
    as_of: date | None = None  # дата события: брать редакцию, действовавшую в тот день (None — действующую)
    act_dates: dict[str, date] | None = None  # акт → дата для выбора его редакции (если точной на as_of нет)
    per_point: int = 2  # не больше N подпунктов одного пункта в выдаче (иначе 5 подпунктов одного перечня вытесняют всё)
    per_article: int = 3  # не больше N единиц одной статьи (кроме статьи, названной в вопросе)
    level_weights: dict[int, float] | None = None  # уровень иерархии акта → множитель RRF (None — LEVEL_WEIGHTS)
    xref_limit: int = 4  # сколько норм, на которые ссылаются найденные пункты, добавить к выдаче (0 — не добавлять)
    xref_from: int = 5  # из скольких лучших результатов брать отсылки


@dataclass
class Result:
    unit_id: str
    path: str
    act_code: str
    article: str | None
    content: str  # на языке ответа, если есть
    contents: dict[str, str]  # {lang: content}
    chunk_ids: dict[str, str]  # {lang: chunk_id}
    rrf: float = 0.0
    rerank: float | None = None
    channels: dict[str, int] = field(default_factory=dict)  # канал → лучший ранг
    pinned: bool = False
    meta: dict = field(default_factory=dict)  # payload чанка: path, point, breadcrumb, valid_from, version_id


@dataclass
class SearchTrace:
    timings_ms: dict[str, float] = field(default_factory=dict)
    candidates: int = 0


def _scroll_ref(client, ref: Ref, act_codes: list[str] | None, as_of: date | None = None,
                act_dates: dict[str, date] | None = None):
    must = [
        vs.time_filter(as_of, act_dates),
        models.FieldCondition(key="article", match=models.MatchValue(value=ref.article)),
    ]
    codes = [ref.act_code] if ref.act_code else act_codes
    if codes:
        must.append(models.FieldCondition(key="act_code", match=models.MatchAny(any=codes)))
    if ref.point:
        must.append(models.FieldCondition(key="point", match=models.MatchValue(value=ref.point)))
    points, _ = client.scroll(vs.COLLECTION, scroll_filter=models.Filter(must=must), limit=200, with_payload=True)
    return points


# Приоритет по иерархии: если закон и приказ говорят об одном и том же (кворум есть и в ЗРК «О жилищных
# отношениях», и в Правилах принятия решений), первым должен идти закон — на него и ссылаться.
# Множитель мягкий: приказ всё равно побеждает, когда он заметно точнее отвечает на вопрос.
LEVEL_WEIGHTS: dict[int, float] = {5: 0.85}


@lru_cache
def _levels() -> dict[str, int]:
    from ingest.sources import load_sources

    return {code: src.hierarchy_level for code, src in load_sources().items()}


# «ГК» в вопросе может означать любую из двух частей Гражданского кодекса: ищем в обеих.
ACT_FAMILIES = {"GK_GEN": ["GK_GEN", "GK_SPEC"], "GK_SPEC": ["GK_SPEC", "GK_GEN"]}


def _exact_hits(client, refs: list[Ref], act_codes: list[str] | None, as_of: date | None = None,
                act_dates: dict[str, date] | None = None) -> list[vs.Hit]:
    hits: list[vs.Hit] = []
    for ref in refs:
        points = []
        for code in ACT_FAMILIES.get(ref.act_code or "", [ref.act_code]):
            r = Ref(ref.article, ref.point, ref.subpoint, code)
            points = _scroll_ref(client, r, act_codes, as_of, act_dates)
            if not points and ref.point:  # пункта нет (опечатка/другая нумерация) — берём статью целиком
                points = _scroll_ref(client, Ref(ref.article, act_code=code), act_codes, as_of, act_dates)
            if points:
                break
        hits.extend(vs.Hit(str(p.id), 1.0, p.payload or {}) for p in points)
    return hits


def search(req: SearchRequest) -> tuple[list[Result], SearchTrace]:
    trace = SearchTrace()
    client = vs.get_client()

    t0 = time.perf_counter()
    encoded = get_embedder().encode(req.queries, max_length=256)
    trace.timings_ms["embed"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    ranked_lists: list[tuple[str, float, list[vs.Hit]]] = []
    for i, enc in enumerate(encoded):
        ranked_lists.append((f"dense{i}", 1.0, vs.search_dense(client, enc.dense, req.per_channel,
                                                               act_codes=req.act_codes, as_of=req.as_of, act_dates=req.act_dates)))
        ranked_lists.append((f"sparse{i}", 1.0, vs.search_sparse(client, enc.sparse, req.per_channel,
                                                                 act_codes=req.act_codes, as_of=req.as_of,
                                                                 act_dates=req.act_dates)))
    exact = _exact_hits(client, req.refs, req.act_codes, req.as_of, req.act_dates) if req.refs else []
    if exact:
        ranked_lists.append(("exact", EXACT_WEIGHT, exact))
    trace.timings_ms["search"] = (time.perf_counter() - t0) * 1000

    # RRF по единицам (kk и ru версии одного пункта складываются — совпадение на двух языках сильнее)
    units: dict[str, Result] = {}
    exact_units = {h.payload["unit_id"] for h in exact}
    for channel, weight, hits in ranked_lists:
        seen_in_list: set[str] = set()
        for rank, h in enumerate(hits, start=1):
            p = h.payload
            uid = p["unit_id"]
            r = units.get(uid)
            if r is None:
                r = units[uid] = Result(unit_id=uid, path=p["path"], act_code=p["act_code"], article=p.get("article"),
                                        content="", contents={}, chunk_ids={}, pinned=uid in exact_units,
                                        meta={k: p.get(k) for k in ("point", "valid_from", "valid_to", "version_id", "is_current",
                                                                     "temporal")})
            r.contents.setdefault(p["lang"], p["content"])
            r.meta.setdefault(f"breadcrumb_{p['lang']}", p.get("breadcrumb"))
            r.chunk_ids.setdefault(p["lang"], h.chunk_id)
            if uid in seen_in_list:
                continue
            seen_in_list.add(uid)
            r.rrf += weight / (RRF_K + rank)
            base = channel.rstrip("0123456789")
            r.channels[base] = min(r.channels.get(base, rank), rank)

    weights = LEVEL_WEIGHTS if req.level_weights is None else req.level_weights
    levels = _levels() if weights else {}
    for r in units.values():
        r.content = r.contents.get(req.reply_lang) or next(iter(r.contents.values()))
        if not r.pinned:
            r.rrf *= weights.get(levels.get(r.act_code, 0), 1.0)
    pool = sorted(units.values(), key=lambda r: r.rrf, reverse=True)
    trace.candidates = len(pool)

    settings = get_settings()
    use_reranker = settings.rerank_enabled if req.use_reranker is None else req.use_reranker
    rerank_pool = req.rerank_pool or settings.rerank_pool
    if use_reranker and pool:
        t0 = time.perf_counter()
        head = pool[:rerank_pool]
        # Закреплённые точные ссылки всегда участвуют в реранкинге, даже если RRF их не поднял.
        head += [r for r in pool[rerank_pool:] if r.pinned][:10]
        scores = get_reranker().score(req.rerank_query, [r.content for r in head],
                                      max_length=settings.rerank_max_length, batch_size=10)
        for r, s in zip(head, scores):
            r.rerank = s
        # тот же приоритет иерархии, что и для RRF
        pool = sorted(head, key=lambda r: (r.rerank or 0.0) * (1.0 if r.pinned else weights.get(levels.get(r.act_code, 0), 1.0)),
                      reverse=True)
        trace.timings_ms["rerank"] = (time.perf_counter() - t0) * 1000

    results = diversify(pool, req.top_k, req.per_point, req.per_article)
    # Явно названная статья должна попасть в выдачу хотя бы лучшим своим пунктом.
    for pinned in [r for r in pool if r.pinned]:
        if not any(x.article == pinned.article and x.act_code == pinned.act_code for x in results):
            results = results[:-1] + [pinned] if len(results) >= req.top_k else results + [pinned]
    if req.xref_limit and results:
        t0 = time.perf_counter()
        results += expand_xrefs(client, results, encoded[0].dense, req)
        trace.timings_ms["xrefs"] = (time.perf_counter() - t0) * 1000
    return results, trace


def diversify(pool: list[Result], k: int, per_point: int, per_article: int) -> list[Result]:
    """Лучшие k единиц, но без засилья одного перечня: подпункты «art51-5/p2/sp7», «…/sp10», «…/sp12»
    почти одинаково близки к вопросу и вытесняли из выдачи другие статьи. Явно названные статьи не ограничиваем."""
    if per_point <= 0 and per_article <= 0:
        return pool[:k]
    out: list[Result] = []
    rest: list[Result] = []
    by_point: Counter = Counter()
    by_article: Counter = Counter()
    for r in pool:
        point_key = (r.act_code, r.path.split("/sp")[0])
        article_key = (r.act_code, r.article or r.path.split("/")[0])
        if not r.pinned and ((per_point and by_point[point_key] >= per_point)
                             or (per_article and by_article[article_key] >= per_article)):
            rest.append(r)
            continue
        out.append(r)
        by_point[point_key] += 1
        by_article[article_key] += 1
        if len(out) == k:
            return out
    return out + rest[: k - len(out)]


def _unit_result(points, uid: str, reply_lang: str, xref_from: str) -> Result:
    p0 = points[0].payload or {}
    r = Result(unit_id=uid, path=p0["path"], act_code=p0["act_code"], article=p0.get("article"), content="",
               contents={}, chunk_ids={},
               meta={k: p0.get(k) for k in ("point", "valid_from", "valid_to", "version_id", "is_current", "temporal")})
    for pt in points:
        p = pt.payload or {}
        r.contents.setdefault(p["lang"], p["content"])
        r.chunk_ids.setdefault(p["lang"], str(pt.id))
        r.meta.setdefault(f"breadcrumb_{p['lang']}", p.get("breadcrumb"))
    r.content = r.contents.get(reply_lang) or next(iter(r.contents.values()))
    r.meta["xref_from"] = xref_from
    r.channels["xref"] = 1
    return r


def _resolve_xref(client, x: XRef, dense: list[float], req: SearchRequest) -> tuple[str, list] | None:
    """Пункт, на который ссылается норма; для ссылки на статью целиком — ближайший к вопросу пункт статьи."""
    for code in ACT_FAMILIES.get(x.act_code, [x.act_code]):
        if x.point:
            pts = _scroll_ref(client, Ref(x.article, x.point, act_code=code), None, req.as_of, req.act_dates)
            if pts:
                return pts[0].payload["unit_id"], pts
        flt = models.Filter(must=[
            vs.time_filter(req.as_of, req.act_dates),
            models.FieldCondition(key="act_code", match=models.MatchValue(value=code)),
            models.FieldCondition(key="article", match=models.MatchValue(value=x.article)),
        ])
        best = client.query_points(vs.COLLECTION, query=dense, using=vs.DENSE, limit=1, query_filter=flt,
                                   with_payload=True).points
        if best:
            uid = best[0].payload["unit_id"]
            pts, _ = client.scroll(vs.COLLECTION, scroll_filter=models.Filter(must=[
                vs.time_filter(req.as_of, req.act_dates),
                models.FieldCondition(key="unit_id", match=models.MatchValue(value=uid))]), limit=10, with_payload=True)
            return uid, pts or best
    return None


def expand_xrefs(client, results: list[Result], dense: list[float], req: SearchRequest) -> list[Result]:
    have_units = {r.unit_id for r in results}
    have_articles = {(r.act_code, r.article) for r in results}
    extra: list[Result] = []
    seen: set[XRef] = set()
    for r in results[: req.xref_from]:
        text = r.contents.get("ru") or r.content  # русский текст отсылки распознаём надёжнее
        text = text.split("\n", 1)[1] if "\n" in text else text  # без строки-«хлебных крошек»
        for x in extract_xrefs(text, r.act_code):
            if len(extra) >= req.xref_limit:
                return extra
            # отсылка на статью, которая уже в выдаче, ничего не добавляет; на саму себя — тоже
            if x in seen or (x.point is None and (x.act_code, x.article) in have_articles):
                continue
            if x.act_code == r.act_code and x.article == r.article and x.point in (None, r.meta.get("point")):
                continue
            seen.add(x)
            got = _resolve_xref(client, x, dense, req)
            if got is None or got[0] in have_units:
                continue
            uid, pts = got
            have_units.add(uid)
            extra.append(_unit_result(pts, uid, req.reply_lang, r.path if r.act_code == x.act_code
                                      else f"{r.act_code}:{r.path}"))
    return extra
