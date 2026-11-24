"""Прогон 100 жизненных ситуаций (life_scenarios.jsonl) через API и оценка по независимому эталону.

  python -m tests.eval.run_life_eval --api https://94-131-82-106.sslip.io/backend --tag before
  python -m tests.eval.run_life_eval --api ... --tag after --ids nb01,cx01
  python -m tests.eval.run_life_eval --report reports/life-before.jsonl reports/life-after.jsonl   # сравнение

Эталон написан по тексту норм из базы (не моделью): в каждом сценарии — нужные нормы (sources), обязательные выводы
(must), заведомо ошибочные выводы (must_not), ожидаемое поведение (expect):
  answer      — ответ по существу;
  clarify     — без факта вывод невозможен → нужен уточняющий вопрос;
  gap         — нормы нет в базе → система должна признать ограничение, а не отвечать «по памяти»;
  allegation  — пользователь выдаёт обвинение за факт → ответ не должен принимать его как доказанное.

Оценка автоматическая и грубая (регулярные выражения по выводам) — это не экспертиза. Итоговая разметка:
  correct  — все обязательные выводы есть, нормы найдены, поведение верное, ошибочных выводов нет;
  partial  — ошибочных выводов нет, но что-то пропущено (вывод, норма, подвопрос);
  wrong    — есть заведомо ошибочный вывод, неверный вердикт или неверное поведение (ответил без базы / не ответил).
Каждый ответ сохраняется целиком, чтобы юрист мог проверить разметку.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
REPORTS = HERE / "reports"

ADMIT = re.compile(r"не найден|нет в базе|в базе (портала )?(нет|не )|отсутству\w* в базе|не содерж\w* (норм|в базе)|"
                   r"за пределами|вне (моей )?(специализ|компетенц)|не регулир|недостаточно (норм|правов)|"
                   r"базада (жоқ|табылмады)|табылмады|қамтылмаған", re.I)
EVIDENCE = re.compile(r"доказ|подтвержд|не установлен|презумпц|проверк|дәлел", re.I)
ART_REF = re.compile(r"(?:ст\.|стать[яиеюй])\s*(\d+(?:-\d+)?)|(\d+(?:-\d+)?)-?\s*бап", re.I)


def answer_text(a: dict) -> str:
    """Весь текст ответа, который видит пользователь."""
    parts = [a.get(k, "") or "" for k in ("verdict_text", "summary", "legal_answer")]
    parts += a.get("assumptions") or []
    parts += [f"{b.get('quote', '')} {b.get('explanation', '')}" for b in a.get("legal_basis") or []]
    parts += [f"{r.get('party', '')} {r.get('reason', '')}" for r in a.get("responsibility") or []]
    ass = a.get("assessment") or {}
    parts += [ass.get("reasoning", "")] + list(ass.get("risks") or [])
    parts += [f"{s.get('step', '')} {s.get('who', '')} {s.get('where', '')} {s.get('deadline', '')} "
              + " ".join(s.get("evidence") or []) for s in a.get("action_plan") or []]
    parts += [f"{c.get('item', '')} {c.get('rule', '')} {c.get('result', '')}" for c in a.get("calculations") or []]
    parts += [f"{d.get('title', '')} {d.get('text', '')}" for d in a.get("drafts") or []]
    parts += [f"{x.get('point', '')} {x.get('why', '')}" for x in a.get("attention") or []]
    parts += a.get("clarifying_questions") or []
    return "\n".join(p for p in parts if p)


def _has(path: str, goal: str) -> bool:
    return path == goal or path.startswith(goal + "/")


def source_hit(group: str, sources: list[dict]) -> bool:
    """group: «ACT:path|ACT:path» или «ACT» (любая норма акта)."""
    for alt in group.split("|"):
        act, _, path = alt.partition(":")
        if any((s.get("act_code") or s.get("act")) == act and (not path or _has(s.get("path", ""), path))
               for s in sources):
            return True
    return False


def ungrounded_articles(text: str, sources: list[dict]) -> list[str]:
    """Номера статей в ответе, которых нет среди найденных норм — кандидаты на выдуманные ссылки."""
    known = {s.get("path", "").split("/")[0][3:] for s in sources if s.get("path", "").startswith("art")}
    known |= {str(s.get("article")) for s in sources if s.get("article")}
    found = {m.group(1) or m.group(2) for m in ART_REF.finditer(text)}
    return sorted(n for n in found if n not in known)


def cause(case, label, bad, verdict_ok, behavior_ok, miss_src, miss_must, split_ok, exp) -> str | None:
    """Предварительная причина ошибки (по ТЗ, п. 8) — уточняется при ручном разборе."""
    if label == "correct":
        return None
    if not behavior_ok and exp == "gap":
        return "неполная база + ответ без признания пробела"
    if not behavior_ok and exp == "allegation":
        return "неправильное понимание фактов (обвинение принято как факт)"
    if not behavior_ok and exp == "clarify":
        return "не запрошены недостающие факты"
    if not behavior_ok:
        return "сбой системы / нет ответа"
    if not split_ok:
        return "потерян вопрос (декомпозиция)"
    if bad or not verdict_ok:
        return "ошибка юридического рассуждения" + (" (нужная норма не найдена)" if miss_src else "")
    if miss_src and case.get("coverage") == "gap":
        return "неполная законодательная база"
    if miss_src:
        return "ошибка поиска"
    if miss_must:
        return "недостаточный анализ (вывод не сделан при найденной норме)"
    return "прочее"


def grade(case: dict, sources: list[dict], answer: dict, analysis: dict, mode: str | None) -> dict:
    text = answer_text(answer)
    low = text.lower()
    miss_src = [g for g in case.get("sources", []) if not source_hit(g, sources)]
    miss_must = [label for pat, label in case.get("must", []) if not re.search(pat, low, re.I)]
    bad = [label for pat, label in case.get("must_not", []) if re.search(pat, low, re.I)]
    subs = len(analysis.get("sub_questions") or []) or 1
    exp = case.get("expect", "answer")
    nf = bool(answer.get("not_found"))
    admitted = nf or bool(ADMIT.search(text))
    behavior_ok, behavior_note = True, ""
    if not answer:
        behavior_ok, behavior_note = False, f"нет ответа ({mode})"
    elif exp == "answer" and nf:
        behavior_ok, behavior_note = False, "не ответил (not_found), хотя нормы в базе есть"
    elif exp == "clarify" and not answer.get("clarifying_questions"):
        behavior_ok, behavior_note = False, "не задал уточняющий вопрос"
    elif exp == "gap" and not admitted:
        behavior_ok, behavior_note = False, "ответил без признания пробела в базе"
    elif exp == "allegation" and not EVIDENCE.search(text):
        behavior_ok, behavior_note = False, "не отделил обвинение от доказанного факта"
    verdict_ok = answer.get("verdict") in case["verdict"] if case.get("verdict") and answer else True
    split_ok = subs >= case.get("min_subquestions", 1)
    drafts_ok = bool(answer.get("drafts")) or not case.get("drafts")
    attention_ok = bool(answer.get("attention")) or not case.get("attention")
    ungrounded = ungrounded_articles(text, sources) if answer else []

    if bad or not verdict_ok or not behavior_ok:
        label = "wrong"
    elif not miss_must and not miss_src and split_ok and drafts_ok:
        label = "correct"
    else:
        label = "partial"
    reasons = ([f"ошибочный вывод: {b}" for b in bad] + ([f"вердикт {answer.get('verdict')} ≠ {case['verdict']}"]
               if not verdict_ok else []) + ([behavior_note] if behavior_note else [])
               + [f"нет вывода: {m}" for m in miss_must] + [f"не найдена норма: {s}" for s in miss_src]
               + ([f"подвопросов {subs} < {case.get('min_subquestions')}"] if not split_ok else [])
               + ([] if drafts_ok else ["нет готового текста"]) + ([] if attention_ok else ["нет «обратите внимание»"]))
    n_must = len(case.get("must", []))
    return {"label": label, "reasons": reasons, "cause": cause(case, label, bad, verdict_ok, behavior_ok, miss_src,
                                                                miss_must, split_ok, exp), "missing_sources": miss_src, "missing_must": miss_must,
            "must_not_hits": bad, "must_recall": (n_must - len(miss_must)) / n_must if n_must else 1.0,
            "source_recall": (1 - len(miss_src) / len(case["sources"])) if case.get("sources") else 1.0,
            "behavior_ok": behavior_ok, "verdict_ok": verdict_ok, "split_ok": split_ok, "attention_ok": attention_ok,
            "drafts_ok": drafts_ok, "not_found": nf, "admitted_gap": admitted, "subquestions": subs,
            "ungrounded_articles": ungrounded, "citations": len(answer.get("legal_basis") or [])}


async def _api_events(api: str, q: str):
    import httpx
    from types import SimpleNamespace

    async with httpx.AsyncClient(timeout=httpx.Timeout(900, connect=30)) as client:
        async with client.stream("POST", f"{api.rstrip('/')}/v1/chat", json={"q": q}) as resp:
            resp.raise_for_status()
            name = None
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    name = line[7:]
                elif line.startswith("data: ") and name:
                    yield SimpleNamespace(name=name, data=json.loads(line[6:]))
                    name = None


async def run_case(case: dict, api: str) -> dict:
    t0 = time.perf_counter()
    sources, answer, analysis, mode = [], {}, {}, None
    for attempt in range(2):  # один повтор при сетевом обрыве
        try:
            async for e in _api_events(api, case["q"]):
                if e.name == "sources":
                    sources = e.data["sources"]
                elif e.name == "answer":
                    answer, analysis, mode = e.data["answer"], e.data.get("analysis") or {}, e.data["mode"]
                elif e.name == "error":
                    mode = f"error: {str(e.data)[:200]}"
            if answer:
                break
            await asyncio.sleep(20)  # ошибка сервера (лимит модели и т.п.) — одна повторная попытка
        except Exception as exc:  # noqa: BLE001
            mode = f"error: {type(exc).__name__}"
            await asyncio.sleep(5)
    g = grade(case, sources, answer, analysis, mode)
    return {"id": case["id"], "category": case["category"], "lang": case["lang"], "expect": case.get("expect"),
            "coverage": case.get("coverage"), "exception": bool(case.get("exception")), "q": case["q"],
            "reference": case.get("ref"), "mode": mode, "seconds": round(time.perf_counter() - t0, 1), **g,
            "fact_check": analysis.get("fact_check"), "sub_questions": analysis.get("sub_questions"),
            "sources": [{"act": s.get("act_code"), "path": s.get("path"), "relation": s.get("relation")} for s in sources],
            "answer": answer}


async def run(cases: list[dict], api: str, out: Path, parallel: int) -> None:
    sem = asyncio.Semaphore(parallel)
    lock = asyncio.Lock()

    async def one(case):
        async with sem:
            res = await run_case(case, api)
        async with lock:
            with out.open("a", encoding="utf-8") as f:
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
            print(f"{res['label']:<8}{res['id']}  {res['seconds']:>6}s  " + "; ".join(res["reasons"][:4]), flush=True)

    await asyncio.gather(*(one(c) for c in cases))


CAT_RU = {"neighbors": "Соседи и конфликты", "pets": "Домашние животные", "osi": "ОСИ, КСК, УК",
          "utilities": "Коммунальные услуги", "money": "Деньги и платежи", "common_property": "Общее имущество",
          "parking": "Парковки и территория", "repair": "Ремонт и перепланировка", "rent": "Аренда жилья",
          "safety": "Безопасность", "developer": "Новостройки и застройщики", "meetings": "Собрания и голосования",
          "complaints": "Жалобы и защита прав", "complex": "Сложные комбинированные"}


def summarize(rows: list[dict]) -> dict:
    n = len(rows) or 1
    exc = [r for r in rows if r["exception"]]
    return {"n": len(rows),
            "correct": sum(r["label"] == "correct" for r in rows), "partial": sum(r["label"] == "partial" for r in rows),
            "wrong": sum(r["label"] == "wrong" for r in rows),
            "accuracy": sum(r["label"] == "correct" for r in rows) / n,
            "completeness": sum(r["must_recall"] for r in rows) / n,
            "source_recall": sum(r["source_recall"] for r in rows) / n,
            "ungrounded_answers": sum(bool(r["ungrounded_articles"]) for r in rows),
            "exceptions": f"{sum(r['label'] == 'correct' for r in exc)}/{len(exc)}" if exc else "—",
            "avg_seconds": sum(r["seconds"] for r in rows) / n}


def load(path: Path) -> list[dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            rows[r["id"]] = r  # повторный прогон кейса заменяет прежний
    return list(rows.values())


MANUAL = HERE / "life_manual.json"


def apply_manual(name: str, rows: list[dict]) -> list[dict]:
    """Ручная разметка (не юрист) поверх автоматической: регулярные выражения не видят ошибок квалификации."""
    if not MANUAL.exists():
        return rows
    over = json.loads(MANUAL.read_text(encoding="utf-8")).get(name, {})
    out = []
    for r in rows:
        o = over.get(r["id"])
        if o:
            r = {**r, "auto_label": r["label"], "label": o["label"], "cause": o.get("cause"), "manual_note": o.get("note")}
        out.append(r)
    return out


def report(paths: list[Path]) -> None:
    runs = [(p.stem, apply_manual(p.stem, load(p))) for p in paths]
    for name, rows in runs:
        auto = sum(r.get("auto_label", r["label"]) == "correct" for r in rows)
        print(f"\n{name}: автоматически верно {auto}/{len(rows)}; ручных поправок {sum('auto_label' in r for r in rows)}")
    for name, rows in runs:
        s = summarize(rows)
        print(f"\n== {name}: {s['n']} сценариев — верно {s['correct']}, частично {s['partial']}, ошибочно {s['wrong']}; "
              f"полнота выводов {s['completeness']:.0%}, нормы найдены {s['source_recall']:.0%}, "
              f"ответов со ссылкой на ненайденную статью {s['ungrounded_answers']}, исключения {s['exceptions']}, "
              f"среднее время {s['avg_seconds']:.0f} с")
        by = defaultdict(list)
        for r in rows:
            by[r["category"]].append(r)
        print(f"  {'категория':<28}{'n':>3}{'верно':>7}{'част.':>7}{'ошиб.':>7}{'полнота':>9}{'нормы':>7}")
        for cat in CAT_RU:
            if cat in by:
                c = summarize(by[cat])
                print(f"  {CAT_RU[cat]:<28}{c['n']:>3}{c['correct']:>7}{c['partial']:>7}{c['wrong']:>7}"
                      f"{c['completeness']:>9.0%}{c['source_recall']:>7.0%}")
        for exp in ("gap", "clarify", "allegation"):
            sub = [r for r in rows if r["expect"] == exp]
            if sub:
                print(f"  поведение «{exp}»: верно {sum(r['behavior_ok'] for r in sub)}/{len(sub)}")
    if len(runs) == 2:
        (a_name, a), (b_name, b) = runs
        bi = {r["id"]: r for r in b}
        order = {"wrong": 0, "partial": 1, "correct": 2}
        better = [r["id"] for r in a if r["id"] in bi and order[bi[r["id"]]["label"]] > order[r["label"]]]
        worse = [r["id"] for r in a if r["id"] in bi and order[bi[r["id"]]["label"]] < order[r["label"]]]
        print(f"\n{a_name} → {b_name}: улучшились {len(better)} {better}\n  ухудшились {len(worse)} {worse}")


def regrade(path: Path, scenarios: Path) -> None:
    cases = {c["id"]: c for c in (json.loads(l) for l in scenarios.read_text(encoding="utf-8").splitlines() if l.strip())}
    rows = load(path)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            c = cases.get(r["id"])
            if c:
                analysis = {"sub_questions": r.get("sub_questions") or []}
                r.update(grade(c, r["sources"], r["answer"], analysis, r["mode"]))
                r["reference"] = c.get("ref")
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    report([path])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api")
    ap.add_argument("--file", default=str(HERE / "life_scenarios.jsonl"))
    ap.add_argument("--ids")
    ap.add_argument("--tag", default="run")
    ap.add_argument("--parallel", type=int, default=2)
    ap.add_argument("--resume", action="store_true", help="пропустить сценарии, уже записанные в отчёт с этим тегом")
    ap.add_argument("--report", nargs="+", help="напечатать сводку по готовым отчётам (один или два для сравнения)")
    ap.add_argument("--regrade", help="пересчитать оценки отчёта по текущему эталону (без запросов к модели)")
    args = ap.parse_args()
    if args.report:
        report([Path(p) for p in args.report])
        return
    if args.regrade:
        regrade(Path(args.regrade), Path(args.file))
        return
    cases = [json.loads(l) for l in Path(args.file).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.ids:
        wanted = set(args.ids.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"life-{args.tag}.jsonl"
    if args.resume and out.exists():
        done = {r["id"] for r in load(out) if r["answer"]}
        cases = [c for c in cases if c["id"] not in done]
    asyncio.run(run(cases, args.api, out, args.parallel))
    report([out])


if __name__ == "__main__":
    main()
