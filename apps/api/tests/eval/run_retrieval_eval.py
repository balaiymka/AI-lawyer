"""Оценка поиска по золотому набору вопросов.

  python -m tests.eval.run_retrieval_eval                 # нормализация без LLM (запасной режим)
  python -m tests.eval.run_retrieval_eval --llm           # нормализатор Claude (нужен ANTHROPIC_API_KEY)
  python -m tests.eval.run_retrieval_eval --no-rerank     # без реранкера (абляция)

Попадание: найденная единица совпадает с эталонной или вложена в неё
(эталон «art40» засчитывает любой пункт статьи 40). Отчёт пишется в tests/eval/reports/.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from app.services.nlu.normalizer import normalize_heuristic, normalize_llm, to_search_request
from app.services.rag.retriever import search

HERE = Path(__file__).parent
GOLD = HERE / "retrieval_gold.jsonl"


def is_hit(path: str, gold: list[str]) -> bool:
    """path — «ACT:art42/p8». Эталон без кода акта («art42/p8») совпадает с этим путём в любом акте."""
    act, _, bare = path.partition(":")
    for g in gold:
        g_act, sep, g_path = g.partition(":")
        if not sep:
            g_act, g_path = None, g
        if g_act and g_act != act:
            continue
        if bare == g_path or bare.startswith(g_path + "/"):
            return True
    return False


def first_hit_rank(paths: list[str], gold: list[str]) -> int | None:
    for i, p in enumerate(paths, start=1):
        if is_hit(p, gold):
            return i
    return None


def load_gold(only: str | None = None, limit: int | None = None) -> list[dict]:
    items = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    if only:
        items = [i for i in items if i["id"] in only.split(",")]
    return items[:limit] if limit else items


def recall(rs: list[dict], k: int) -> float:
    return sum(1 for r in rs if r["rank"] and r["rank"] <= k) / len(rs) if rs else 0.0


def mrr(rs: list[dict]) -> float:
    return sum(1 / r["rank"] for r in rs if r["rank"]) / len(rs) if rs else 0.0


def eval_one(item: dict, nq, no_rerank: bool = False) -> dict:
    req = to_search_request(item["q"], nq, top_k=10)
    if no_rerank:
        req.use_reranker = False
    results, trace = search(req)
    paths = [f"{r.act_code}:{r.path}" for r in results if not r.meta.get("xref_from")]
    xrefs = [f"{r.act_code}:{r.path}" for r in results if r.meta.get("xref_from")]
    return {**item, "rank": first_hit_rank(paths, item["gold"]), "top": paths[:5], "xrefs": xrefs,
            "reply_lang": nq.reply_lang, "timings": trace.timings_ms}


def summarize(rows: list[dict], mode: str, elapsed: float) -> dict:
    by_style = defaultdict(list)
    by_act = defaultdict(list)
    for r in rows:
        by_style[r["style"]].append(r)
        acts = {g.partition(":")[0] for g in r["gold"] if ":" in g} or {"ZHO"}
        for a in acts:
            by_act[a].append(r)
    return {
        "mode": mode, "n": len(rows), "recall@1": recall(rows, 1), "recall@5": recall(rows, 5),
        "recall@10": recall(rows, 10), "mrr": mrr(rows), "sec_per_query": elapsed / max(len(rows), 1),
        "by_style": {s: {"n": len(rs), "recall@10": recall(rs, 10), "recall@1": recall(rs, 1)}
                     for s, rs in sorted(by_style.items())},
        "by_act": {a: {"n": len(rs), "recall@10": recall(rs, 10)} for a, rs in sorted(by_act.items())},
    }


def write_report(summary: dict, rows: list[dict]) -> Path:
    mode = summary["mode"]
    out = HERE / "reports"
    out.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    path = out / f"{stamp}-{mode}.json"
    path.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    misses = [r for r in rows if not r["rank"] or r["rank"] > 10]
    lines = [f"# Промахи ({mode}): {len(misses)} из {len(rows)}", ""]
    for r in misses:
        lines.append(f"- **{r['id']}** [{r['style']}] {r['q']}  \n  эталон: {r['gold']} · найдено: {r['top']}")
    (out / f"{stamp}-{mode}-misses.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_heuristic(items: list[dict], log=print, no_rerank: bool = False) -> tuple[dict, list[dict]]:
    """Синхронный прогон без LLM — так его запускает и админка (в фоне, внутри API)."""
    rows = []
    t0 = time.perf_counter()
    for item in items:
        row = eval_one(item, normalize_heuristic(item["q"]), no_rerank)
        rows.append(row)
        mark = f"@{row['rank']}" if row["rank"] else "MISS"
        log(f"{item['id']} [{item['style']:5}] {mark:>5}  {item['q'][:70]}")
    mode = "heuristic" + ("-norerank" if no_rerank else "")
    return summarize(rows, mode, time.perf_counter() - t0), rows


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only")
    args = ap.parse_args()
    items = load_gold(args.only, args.limit)

    if args.llm:
        rows = []
        t0 = time.perf_counter()
        for item in items:
            row = eval_one(item, await normalize_llm(item["q"]), args.no_rerank)
            rows.append(row)
            print(f"{item['id']} {('@' + str(row['rank'])) if row['rank'] else 'MISS'}  {item['q'][:70]}")
        summary = summarize(rows, "llm" + ("-norerank" if args.no_rerank else ""), time.perf_counter() - t0)
    else:
        summary, rows = run_heuristic(items, no_rerank=args.no_rerank)
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    write_report(summary, rows)


if __name__ == "__main__":
    asyncio.run(main())
