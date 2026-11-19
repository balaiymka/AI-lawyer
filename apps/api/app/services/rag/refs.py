"""Распознавание явных ссылок на нормы в тексте пользователя: «ст 42 п 8», «42-баптың 8-тармағы», «КоАП 4xx».

Номера статей никогда не ищем «по смыслу» — только точным совпадением.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

L = r"а-яёәғқңөұүһіa-z"  # буквы, после которых «ст»/«п» не являются сокращением
NUM = r"(\d+(?:-\d+)?)"

ARTICLE_WORD = r"(?:статья|статьи|статье|статью|статей|ст\.?|statya|stat'ya|st\.)"
POINT_WORD = r"(?:пункт[а-я]*|п\.|п|punkt)"
SUBPOINT_WORD = r"(?:подпункт[а-я]*|пп\.?)"
KK_ARTICLE = r"(?:бап|баб|bap)[а-яәғқңөұүһі]*"
KK_POINT = r"(?:тармақ|тармак|тармағ|тармаг|tarmaq|tarmak)[а-яәғқңөұүһі]*"

RU_ART_FIRST = re.compile(
    rf"(?<![{L}]){ARTICLE_WORD}\s*{NUM}"
    rf"(?:\s*,?\s*{POINT_WORD}\s*(\d+))?"
    rf"(?:\s*,?\s*{SUBPOINT_WORD}\s*(\d+))?",
    re.I,
)
RU_POINT_FIRST = re.compile(
    rf"(?<![{L}]){POINT_WORD}\s*(\d+)\s*,?\s*{ARTICLE_WORD}\s*{NUM}", re.I
)
RU_NUM_FIRST = re.compile(rf"(?<![\d-]){NUM}\s*(?:статья|статьи|статье)(?![{L}])", re.I)
KK_ART = re.compile(
    rf"(?<![\d-]){NUM}\s*-?\s*{KK_ARTICLE}(?:\s*{NUM}\s*-?\s*{KK_POINT})?", re.I
)
KK_POINT_FIRST = re.compile(rf"(?<![\d-]){NUM}\s*-?\s*{KK_POINT}\s*,?\s*{NUM}\s*-?\s*{KK_ARTICLE}", re.I)

ACT_HINTS: list[tuple[str, re.Pattern[str]]] = [
    # Порядок важен: сначала более узкие названия. «УК» в ЖКХ — управляющая компания, поэтому Уголовный
    # кодекс узнаём только по полному названию или «УК РК».
    ("CONST", re.compile(r"конституци|ата\s+заң", re.I)),
    ("GPK", re.compile(r"(?<![а-яё])гпк(?![а-яё])|гражданск\w*\s+процессуальн|азаматтық\s+процест|(?<![а-яәё])апк(?![а-яё])", re.I)),
    ("APPK", re.compile(r"аппк|административн\w*\s+процедурн|әкімшілік\s+рәсімдік|әрпк", re.I)),
    ("KOAP", re.compile(r"коап|административн\w*\s+правонаруш|әқбтк|экбтк|koap|әкімшілік\s+құқық\s+бұзушылық", re.I)),
    ("UK", re.compile(r"уголовн\w*\s+кодекс|(?<![а-яё])ук\s+рк(?![а-яё])|қылмыстық\s+кодекс", re.I)),
    ("GK_SPEC", re.compile(r"гк\s*\(?особ|особенн\w*\s+част|ерекше\s+бөлім", re.I)),
    ("GK_GEN", re.compile(r"(?<![а-яё])гк(?![а-яё])|гражданск\w*\s+кодекс|азаматтық\s+кодекс", re.I)),
    ("METHOD_BUDGET", re.compile(r"методик\w*\s+расч|есептеу\s+әдістеме", re.I)),
    ("RULES_DECISIONS", re.compile(r"правил\w*\s+приняти\w*\s+решени|шешімдер\s+қабылдау\s+қағида", re.I)),
    ("RULES_MGMT", re.compile(r"правил\w*\s+по\s+управлени\w*\s+объект|басқару\s+жөніндегі\s+қағида", re.I)),
    ("COMM_SERVICES", re.compile(r"правил\w*\s+предоставлени\w*\s+коммунальн|коммуналдық\s+қызмет\w*\s+көрсету", re.I)),
    ("CONSUMER", re.compile(r"защит\w*\s+прав\s+потребител|тұтынушылардың\s+құқықтарын\s+қорғау", re.I)),
    ("MONOPOLIES", re.compile(r"естественн\w*\s+монопол|табиғи\s+монопол", re.I)),
    ("STROY", re.compile(r"строительн\w*\s+кодекс|құрылыс\s+кодекс", re.I)),
    ("ZHO", re.compile(r"жилищн\w*\s+отношени|(?<![а-я])зжо(?![а-я])|тұрғын\s+үй\s+қатынас|турғын\s+уй|жилищн\w*\s+закон", re.I)),
]


@dataclass(frozen=True)
class Ref:
    article: str
    point: str | None = None
    subpoint: str | None = None
    act_code: str | None = None  # None — акт не указан, ищем во всех


def _act_hint(text: str) -> str | None:
    for code, pattern in ACT_HINTS:
        if pattern.search(text):
            return code
    return None


def extract_refs(text: str) -> list[Ref]:
    act = _act_hint(text)
    found: list[Ref] = []

    def add(article: str, point: str | None = None, subpoint: str | None = None) -> None:
        ref = Ref(article=article, point=point, subpoint=subpoint, act_code=act)
        # более точная ссылка поглощает менее точную на ту же статью
        for i, r in enumerate(found):
            if r.article == article:
                if (point and not r.point) or (subpoint and not r.subpoint):
                    found[i] = ref
                return
        found.append(ref)

    # Порядок важен: сначала самые точные шаблоны; совпадение, перекрывающее уже найденное, пропускаем
    # (иначе «пункту 17 статьи 42» дало бы ещё и ложную «статью 17»).
    taken: list[tuple[int, int]] = []

    def free(m: re.Match[str]) -> bool:
        s, e = m.span()
        if any(s < te and ts < e for ts, te in taken):
            return False
        taken.append((s, e))
        return True

    for m in RU_POINT_FIRST.finditer(text):
        if free(m):
            add(m.group(2), m.group(1))
    for m in RU_ART_FIRST.finditer(text):
        if free(m):
            add(m.group(1), m.group(2), m.group(3))
    for m in KK_POINT_FIRST.finditer(text):
        if free(m):
            add(m.group(2), m.group(1))
    for m in KK_ART.finditer(text):
        if free(m):
            add(m.group(1), m.group(2))
    for m in RU_NUM_FIRST.finditer(text):
        if free(m):
            add(m.group(1))
    return found
