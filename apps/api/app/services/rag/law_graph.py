"""Закон как граф: какие пункты ссылаются на какие (внутри одного акта).

Пример, на котором ломался AI-юрист. П. 8 ст. 42 ЗРК «О жилищных отношениях»:
  «Решение принимается … большинством … принявших участие в голосовании, за исключением вопросов,
   указанных в подпунктах 6) –16) и 21) пункта 5 настоящей статьи, по которым … большинства от общего числа».
Сам по себе п. 8 не говорит, какие это вопросы, а пп. 7) п. 5 («утверждение размера текущих взносов») не говорит,
каким большинством он принимается. Смысл — только в паре. Поэтому при загрузке закона мы разбираем такие
отсылки и храним рёбра в таблице legal_refs (from_unit → to_unit, kind = exception | reference), а при поиске
к найденному пункту подтягиваем связанные в обе стороны.

Разбираем русский текст (пути пунктов у kk и ru одинаковые). Распознаём только однозначные отсылки внутри акта:
  «подпункт(ах) 6) –16) и 21) пункта 5 настоящей статьи», «пунктом 3 настоящей статьи»,
  «подпунктами 1) и 2) настоящего пункта», «частью третьей настоящей статьи» (часть = пункт),
  «пунктах 1 и 2 статьи 346 настоящего Кодекса», «статьей 25 настоящего Закона», «пунктом 5 настоящих Правил».
Отсылки в другие акты подтягивает xrefs.py во время поиска.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ORDINALS = {
    "перв": 1, "втор": 2, "трет": 3, "четверт": 4, "пят": 5, "шест": 6, "седьм": 7, "восьм": 8, "девят": 9,
    "десят": 10, "одиннадцат": 11, "двенадцат": 12, "тринадцат": 13, "четырнадцат": 14, "пятнадцат": 15,
    "шестнадцат": 16, "семнадцат": 17, "восемнадцат": 18, "девятнадцат": 19, "двадцат": 20,
}
_ORD = r"(?:" + "|".join(sorted(ORDINALS, key=len, reverse=True)) + r")\w*"
_SEP = r"\s*(?:,|–|—|-|\bи\b|\bили\b)\s*"
SP_LIST = rf"\d+\)(?:{_SEP}\d+\))*"
P_LIST = rf"\d+(?:{_SEP}\d+)*"
ORD_LIST = rf"{_ORD}(?:{_SEP}{_ORD})*"
A_LIST = r"\d+(?:-\d+)?(?:\s*(?:,|\bи\b)\s*\d+(?:-\d+)?)*"

REF = re.compile(
    rf"(?:подпункт\w*\s+(?P<sp>{SP_LIST})\s*,?\s*)?"
    rf"(?:(?:пункт\w*\s+(?P<p>{P_LIST})|част(?:ь|и|ью|ями|ях|ей)\s+(?P<part>{ORD_LIST}))\s*,?\s*)?"
    rf"(?P<anchor>настоящей\s+статьи"
    rf"|настоящего\s+пункта"
    rf"|стать(?:я|и|е|ю|ей|ями|ях)\s+(?P<art>{A_LIST})\s+настоящ\w+\s+(?:закона|кодекса|правил|положения|методики|приказа)"
    rf"|настоящ(?:их|его|ей)\s+(?:правил|положения|методики|приказа))",
    re.I,
)
EXCEPTION = re.compile(r"за\s+исключением|кроме|не\s+распространя|не\s+применя", re.I)
MAX_TARGETS = 40


@dataclass(frozen=True)
class GraphRef:
    target: str  # путь единицы в том же акте: art42/p5/sp7
    kind: str  # exception | reference


def _numbers(s: str) -> list[int]:
    """«6) –16) и 21)» → 6..16, 21; «1, 3 и 5» → 1, 3, 5."""
    out: list[int] = []
    for m in re.finditer(r"(\d+)\)?(?:\s*[–—-]\s*(\d+)\)?)?", s):
        a, b = int(m.group(1)), m.group(2)
        rng = range(a, int(b) + 1) if b and 0 < int(b) - a <= MAX_TARGETS else [a]
        out.extend(x for x in rng if x not in out)
    return out[:MAX_TARGETS]


def _ordinals(s: str) -> list[int]:
    out = []
    for w in re.findall(r"[а-яё]+", s.lower()):
        for stem, n in sorted(ORDINALS.items(), key=lambda kv: len(kv[0]), reverse=True):
            if w.startswith(stem):
                out.append(n)
                break
    return out


def _prefix(path: str, kind: str) -> str | None:
    """Путь до статьи (kind='art') или до пункта (kind='p') включительно."""
    parts = path.split("/")
    for i, seg in enumerate(parts):
        if kind == "art" and seg.startswith("art"):
            return "/".join(parts[: i + 1])
        if kind == "p" and re.fullmatch(r"p\d+(?:-\d+)?(?:~\d+)?", seg):
            return "/".join(parts[: i + 1])
    return None


def _kind(text: str, start: int, end: int) -> str:
    left = re.split(r"[.;\n]", text[:start])[-1]
    return "exception" if EXCEPTION.search(left + text[start:end]) else "reference"


def extract_graph_refs(text: str, own_path: str) -> list[GraphRef]:
    """Отсылки из текста пункта own_path на другие пункты того же акта. Без повторов и без ссылок на себя."""
    found: list[GraphRef] = []

    def add(target: str, kind: str) -> None:
        if target == own_path or own_path.startswith(target + "/") or target.startswith(own_path + "/"):
            return
        if all(r.target != target for r in found):
            found.append(GraphRef(target, kind))

    for m in REF.finditer(text):
        sp = _numbers(m.group("sp")) if m.group("sp") else []
        points = _numbers(m.group("p")) if m.group("p") else _ordinals(m.group("part")) if m.group("part") else []
        anchor = m.group("anchor").lower()
        kind = _kind(text, m.start(), m.end())

        if anchor.startswith("настоящей статьи"):
            base = _prefix(own_path, "art")
            if base is None or not (points or sp):
                continue
            if not points:  # «подпунктом 3) настоящей статьи» — статья без пунктов
                for s in sp:
                    add(f"{base}/sp{s}", kind)
                continue
        elif anchor.startswith("настоящего пункта"):
            base = _prefix(own_path, "p")
            if base is None or not sp or points:
                continue
            for s in sp:
                add(f"{base}/sp{s}", kind)
            continue
        elif m.group("art"):
            arts = re.findall(r"\d+(?:-\d+)?", m.group("art"))
            if len(arts) > 1 or not (points or sp):
                for a in arts:
                    add(f"art{a}", kind)
                continue
            base = f"art{arts[0]}"
        else:  # «пунктом 5 настоящих Правил» — у правил пункты без статей
            if not points:
                continue
            base = None

        for p in points:
            point_path = f"{base}/p{p}" if base else f"p{p}"
            if sp and len(points) == 1:
                for s in sp:
                    add(f"{point_path}/sp{s}", kind)
            else:
                add(point_path, kind)
    return found
