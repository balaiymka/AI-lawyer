"""Поиск норм по вопросу пользователя (без генерации ответа). Используется чатом и для отладки поиска."""

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.services.nlu.normalizer import NormalizedQuery, normalize, to_search_request
from app.services.rag.retriever import search

router = APIRouter(prefix="/search", tags=["search"])


class SearchIn(BaseModel):
    q: str = Field(min_length=2, max_length=4000)
    top_k: int = Field(default=8, ge=1, le=30)


class Source(BaseModel):
    path: str
    act_code: str
    article: str | None
    content: str
    rerank: float | None
    channels: dict[str, int]
    pinned: bool


class SearchOut(BaseModel):
    normalized: NormalizedQuery
    sources: list[Source]
    timings_ms: dict[str, float]


@router.post("", response_model=SearchOut)
async def search_norms(body: SearchIn) -> SearchOut:
    nq = await normalize(body.q)
    req = to_search_request(body.q, nq, top_k=body.top_k)
    results, trace = await run_in_threadpool(search, req)  # torch/Qdrant — синхронные
    return SearchOut(
        normalized=nq,
        sources=[Source(path=r.path, act_code=r.act_code, article=r.article, content=r.content, rerank=r.rerank,
                        channels=r.channels, pinned=r.pinned) for r in results],
        timings_ms=trace.timings_ms,
    )
