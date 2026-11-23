"""Оценка ответов целиком (поиск + граф + ветки + фактчек) на сложных вопросах — вопросы ментора и похожие.

  python -m tests.eval.run_answer_eval                    # все вопросы complex_questions.jsonl
  python -m tests.eval.run_answer_eval --ids m01,m02      # выборочно
  python -m tests.eval.run_answer_eval --api https://94-131-82-106.sslip.io/backend   # через API сервера

Режим --api не грузит модели поиска в этот процесс (на сервере вторая копия моделей не помещается в память).

Нужна подключённая модель (на сервере — Gemini) и база. Каждый вопрос стоит ~$0.05–0.15 (4–7 запросов к модели).
Проверяем автоматически только то, что можно проверить без юриста:
  * sources — нужные пункты попали в контекст (art42/p5 засчитывается и подпунктом art42/p5/sp7);
  * numbers — ключевые числа (кворум, голоса) есть в ответе;
  * drafts — если просили составить текст, он есть;
  * min_subquestions — сообщение разбито на подвопросы.
Смысл ответа читает человек: отчёт с полным ответом пишется в tests/eval/reports/answers-*.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent


CHECKS = ("sources_ok", "numbers_ok", "drafts_ok", "split_ok", "verdict_ok", "attention_ok", "clarifying_ok")
LABELS = {"sources_ok": "нормы найдены", "numbers_ok": "числа верны", "drafts_ok": "готовый текст",
          "split_ok": "вопрос разбит", "verdict_ok": "вывод", "attention_ok": "риски", "clarifying_ok": "уточнение"}


def _answer_text(a: dict) -> str:
    parts = [a.get("verdict_text", ""), a.get("summary", ""), a.get("legal_answer", "")]
    parts += [f"{c['item']} {c['rule']} {c['result']}" for c in a.get("calculations", [])]
    parts += [d["text"] for d in a.get("drafts", [])]
    parts += [b.get("explanation", "") for b in a.get("legal_basis", [])]
    return "\n".join(parts)


def check(case: dict, sources: list[dict], answer: dict, analysis: dict) -> dict:
    paths = [s["path"] for s in sources]
    text = _answer_text(answer)
    miss_src = [g for g in case["sources"] if not any(p == g or p.startswith(g + "/") for p in paths)]
    miss_num = [n for n in case["numbers"] if not re.search(rf"(?<!\d){n}(?!\d)", text)]
    drafts_ok = bool(answer.get("drafts")) or not case.get("drafts")
    subs = len(analysis.get("sub_questions") or []) or 1
    cited = {c for b in answer.get("legal_basis", []) for c in [b.get("chunk_id")]}
    return {"sources_ok": not miss_src, "missing_sources": miss_src, "numbers_ok": not miss_num,
            "missing_numbers": miss_num, "drafts_ok": drafts_ok, "subquestions": subs,
            "split_ok": subs >= case.get("min_subquestions", 1),
            # вывод: ожидаемый вердикт (yes/no/depends), если он однозначен
            "verdict_ok": answer.get("verdict") in case["verdict"] if case.get("verdict") else True,
            # проактивность: есть блок «На что ещё обратить внимание»
            "attention_ok": bool(answer.get("attention")) or not case.get("attention"),
            # нехватка данных: модель спросила нужное, а не угадала
            "clarifying_ok": bool(answer.get("clarifying_questions")) or not case.get("clarifying"),
            "citations": len(cited)}


async def _api_events(api: str, q: str):
    """События SSE /v1/chat — те же, что отдаёт run_chat."""
    import httpx
    from types import SimpleNamespace

    async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=30)) as client:
        async with client.stream("POST", f"{api.rstrip('/')}/v1/chat", json={"q": q}) as resp:
            resp.raise_for_status()
            name = None
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    name = line[7:]
                elif line.startswith("data: ") and name:
                    yield SimpleNamespace(name=name, data=json.loads(line[6:]))
                    name = None


async def run(cases: list[dict], api: str | None = None) -> list[dict]:
    out = []
    for case in cases:
        t0 = time.perf_counter()
        sources, answer, analysis, mode = [], {}, {}, None
        if api:
            events = _api_events(api, case["q"])
        else:
            from app.services.lawyer.pipeline import run_chat

            events = run_chat(case["q"], persist=False)
        try:
            async for e in events:
                if e.name == "sources":
                    sources = e.data["sources"]
                elif e.name == "answer":
                    answer, analysis, mode = e.data["answer"], e.data.get("analysis") or {}, e.data["mode"]
        except Exception as exc:  # noqa: BLE001 — обрыв одного вопроса не должен терять отчёт по остальным
            mode = f"error: {type(exc).__name__}"
        res = {"id": case["id"], "category": case.get("category"), "mode": mode, "seconds": round(time.perf_counter() - t0, 1),
               **check(case, sources, answer, analysis), "fact_check": analysis.get("fact_check"),
               "sub_questions": analysis.get("sub_questions"), "sources": [s["path"] for s in sources],
               "answer": answer, "note": case.get("note")}
        ok = all(res[k] for k in CHECKS)
        fc = (res["fact_check"] or {}).get("verdict", "—")
        print(f"{'OK ' if ok else 'FAIL'} {case['id']}  {res['seconds']:>5}s  подвопросов {res['subquestions']}  "
              f"фактчек {fc}{' (исправлен)' if (res['fact_check'] or {}).get('revised') else ''}"
              + (f"  нет норм {res['missing_sources']}" if res["missing_sources"] else "")
              + (f"  нет чисел {res['missing_numbers']}" if res["missing_numbers"] else "")
              + ("" if res["drafts_ok"] else "  нет готового текста")
              + ("" if res["verdict_ok"] else f"  вердикт {res['answer'].get('verdict')} ≠ {case.get('verdict')}")
              + ("" if res["attention_ok"] else "  нет «обратите внимание»")
              + ("" if res["clarifying_ok"] else "  не задал уточняющий вопрос"), flush=True)
        out.append(res)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", help="через запятую")
    ap.add_argument("--file", default=str(HERE / "complex_questions.jsonl"))
    ap.add_argument("--api", help="адрес API, например https://94-131-82-106.sslip.io/backend")
    args = ap.parse_args()
    cases = [json.loads(l) for l in Path(args.file).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.ids:
        wanted = set(args.ids.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    results = asyncio.run(run(cases, args.api))
    passed = sum(all(r[k] for k in CHECKS) for r in results)
    n = len(results)
    print(f"\nИтого: {passed}/{n} прошли все автоматические проверки")
    print("  " + ", ".join(f"{LABELS[k]} {sum(r[k] for r in results)}/{n}" for k in CHECKS))
    print(f"  среднее время {sum(r['seconds'] for r in results) / max(n, 1):.0f} с; "
          f"фактчек исправил {sum(1 for r in results if (r['fact_check'] or {}).get('revised'))}/{n}")
    print("Смысл ответов проверяет юрист: эталон в поле note, полный ответ — в отчёте.")
    reports = HERE / "reports"
    reports.mkdir(exist_ok=True)
    path = reports / f"answers-{datetime.now():%Y%m%d-%H%M}.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Отчёт: {path}")


if __name__ == "__main__":
    main()
