"""Отсылочные нормы: «в порядке, предусмотренном пунктом 3 статьи 42 настоящего Закона».

Найденный пункт часто сам по себе неполон — смысл лежит в норме, на которую он ссылается.
Здесь мы достаём такие отсылки из текста найденных фрагментов и подтягиваем указанные нормы
(в той же редакции по дате события), чтобы AI-юрист видел их, а не додумывал.

Распознаём только однозначные отсылки:
  - «… статьи N настоящего Закона/Кодекса/Правил» и «осы Заңның/Кодекстің N-бабы» — тот же акт;
  - «… статьи N Закона … «О жилищных отношениях»», «Азаматтық кодекстің N-бабы» — акт по названию.
Отсылки без указания акта («статьи 5» без продолжения) пропускаем: угадывать акт нельзя.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.rag.refs import ACT_HINTS

NUM = r"(\d+(?:-\d+)?)"

# RU: «[подпунктом 1)] [пунктом 3] статьи 42 <хвост>»
RU_ART = re.compile(rf"(?<![а-яё])стать(?:я|и|е|ю|ей|ях|ями)\s+{NUM}(?![\d-])", re.I)
RU_POINT_BEFORE = re.compile(r"пункт(?:а|у|е|ом|ы|ов|ам|ами|ах)?\s+(\d+)\s*,?\s*(?:и\s+\d+\s+)?$", re.I)
RU_SAME_ACT = re.compile(r"^\s*настоящ\w+\s+(?:закона|кодекса|правил|приказа|методики|положения)", re.I)

# KK: «осы Заңның 42-бабы[ның 3-тармағы]», «Азаматтық кодекстің 917-бабы»
KK_ART = re.compile(rf"{NUM}\s*-\s*ба[пб]\w*(?:\s*{NUM}\s*-\s*тармағ\w*)?", re.I)
KK_SAME_ACT = re.compile(r"осы\s+(?:заң\w*|кодекс\w*|қағида\w*|бұйрық\w*|әдістеме\w*)\s*$", re.I)

MAX_FORWARD = 140  # сколько символов после «статьи N» смотрим в поисках названия акта
MAX_BACK = 140


@dataclass(frozen=True)
class XRef:
    act_code: str
    article: str
    point: str | None = None


def _hint(window: str) -> str | None:
    for code, pattern in ACT_HINTS:
        if pattern.search(window):
            return code
    return None


def _clip_forward(s: str) -> str:
    # название акта идёт сразу за номером статьи и до конца фразы
    cut = re.search(r"[;.](?:\s|$)|\n", s)
    return s[: cut.start()] if cut else s


def extract_xrefs(text: str, own_act: str) -> list[XRef]:
    """Отсылки из текста нормы акта own_act. Порядок — как в тексте, без повторов."""
    found: list[XRef] = []

    def add(ref: XRef) -> None:
        if ref not in found:
            found.append(ref)

    for m in RU_ART.finditer(text):
        article = m.group(1)
        forward = _clip_forward(text[m.end(): m.end() + MAX_FORWARD])
        if RU_SAME_ACT.match(forward):
            act = own_act
        else:
            act = _hint(forward[:110])
            if act is None:
                continue
        pm = RU_POINT_BEFORE.search(text[max(0, m.start() - 40): m.start()])
        add(XRef(act, article, pm.group(1) if pm else None))

    for m in KK_ART.finditer(text):
        back = text[max(0, m.start() - MAX_BACK): m.start()]
        back = re.split(r"[;.]\s|\n", back)[-1]
        if KK_SAME_ACT.search(back):
            act = own_act
        else:
            act = _hint(back[-110:])
            if act is None:
                continue
        add(XRef(act, m.group(1), m.group(2)))
    return found
