"""Материалы для проверки юристом: таблица по 100 жизненным ситуациям (до и после исправлений).

  python -m tests.eval.life_review reports/life-before.jsonl reports/life-after.jsonl ../../docs/06-life-review.csv

В таблице: вопрос, независимый эталон, найденные нормы, ответ системы, автоматическая оценка до/после с причинами
и пустые колонки для юриста («оценка юриста», «комментарий»). Автоматическая оценка — не экспертиза.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from tests.eval.run_life_eval import CAT_RU, apply_manual, load

LABEL_RU = {"correct": "верно", "partial": "частично", "wrong": "ошибочно"}


def answer_brief(a: dict) -> str:
    if not a:
        return "— нет ответа —"
    parts = [a.get("verdict_text", ""), a.get("summary", ""), a.get("legal_answer", "")]
    plan = a.get("action_plan") or []
    if plan:
        parts.append("План: " + " → ".join(s.get("step", "") for s in plan))
    att = a.get("attention") or []
    if att:
        parts.append("Обратить внимание: " + "; ".join(x.get("point", "") for x in att))
    if a.get("clarifying_questions"):
        parts.append("Уточнить: " + "; ".join(a["clarifying_questions"]))
    return "\n".join(p for p in parts if p)


def main() -> None:
    before, after, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    b = {r["id"]: r for r in apply_manual(before.stem, load(before))}
    a = {r["id"]: r for r in apply_manual(after.stem, load(after))} if after.exists() else {}
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["id", "категория", "язык", "вопрос", "независимый эталон (по тексту норм)", "покрытие базы",
                     "найденные нормы (после)", "ответ системы (после)", "оценка до", "причины до", "оценка после",
                     "причины после", "причина ошибки", "примечание ручной проверки (не юрист)", "оценка юриста"])
        for rid, rb in b.items():
            ra = a.get(rid, {})
            final = ra or rb
            w.writerow([rid, CAT_RU.get(rb["category"], rb["category"]), rb["lang"], rb["q"], rb.get("reference", ""),
                        rb.get("coverage", ""), ", ".join(f"{s['act']}:{s['path']}" for s in final.get("sources", [])),
                        answer_brief(final.get("answer") or {}), LABEL_RU.get(rb["label"], rb["label"]),
                        "; ".join(rb["reasons"]), LABEL_RU.get(ra.get("label"), "—"), "; ".join(ra.get("reasons", [])),
                        (ra or rb).get("cause") or "", (ra or rb).get("manual_note") or "", ""])
    print(f"{out}: {len(b)} строк")


if __name__ == "__main__":
    main()
