"""Дата события в вопросе: закон применяется в редакции, действовавшей на момент события.

«залил в 2020 году», «2022 жылы онлайн дауыс беру», «15.03.2021», «в марте 2021» → дата.
Год без месяца → 1 июля (середина года; ответ предупреждает, что точную дату стоит уточнить).
Даты реквизитов актов («Закон от 16 апреля 1997 года») не считаются датой события.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

RU_MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7, "август": 8,
             "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}
KK_MONTHS = {"қаңтар": 1, "канта": 1, "ақпан": 2, "акпан": 2, "наурыз": 3, "сәуір": 4, "сауир": 4, "мамыр": 5,
             "маусым": 6, "шілде": 7, "шилде": 7, "тамыз": 8, "қыркүйек": 9, "кыркуйек": 9, "қазан": 10,
             "казан": 10, "қараша": 11, "караша": 11, "желтоқсан": 12, "желтоксан": 12}

FULL_DATE = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](\d{4})(?!\d)")
MONTH_YEAR = re.compile(r"(?<![а-яәғқңөұүһі])([а-яәғқңөұүһі]{3,9})\s+(\d{4})(?!\d)", re.I)
YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)\s*(?:-?(?:м|го|ом)\s*)?(?:год|г\.|г(?![а-я])|жыл|ж\.|ж(?![а-яәғқңөұүһі]))", re.I)
YEAR_PREFIX = re.compile(r"(?:в|с|к|до|после)\s+((?:19|20)\d{2})(?!\d)", re.I)
# «Закон от 16 апреля 1997 года», «приказ … от 2015 года», «редакция 2018 года» — реквизиты, не событие
REQUISITE = re.compile(r"(?:от|редакци\w*|№)\s*(?:\d{1,2}\s*)?(?:[а-яё]+\s+)?$", re.I)
# казахский порядок: «2023 жылғы наурыз», «2021 ж. 5 мамыр»
YEAR_MONTH_KK = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*(?:жылғы|жылы|ж\.)\s*(?:(\d{1,2})\s+)?([а-яәғқңөұүһі]{3,9})", re.I)


@dataclass
class EventDate:
    value: date
    precision: str  # day | month | year
    source: str


def _month(word: str) -> int | None:
    w = word.lower()
    for stem, m in KK_MONTHS.items():
        if w.startswith(stem):
            return m
    for stem, m in RU_MONTHS.items():
        if w.startswith(stem) and (stem != "ма" or w in ("мае", "май", "мая")):
            return m
    return None


def _is_requisite(text: str, start: int) -> bool:
    return bool(REQUISITE.search(text[max(0, start - 25):start]))


def extract_event_date(text: str, today: date | None = None) -> EventDate | None:
    today = today or date.today()
    found: list[EventDate] = []
    for m in FULL_DATE.finditer(text):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            if not _is_requisite(text, m.start()):
                found.append(EventDate(date(y, mo, d), "day", m.group(0)))
        except ValueError:
            pass
    for m in MONTH_YEAR.finditer(text):
        mo = _month(m.group(1))
        if mo and not _is_requisite(text, m.start()):
            found.append(EventDate(date(int(m.group(2)), mo, 15), "month", m.group(0)))
    for m in YEAR_MONTH_KK.finditer(text):
        mo = _month(m.group(3))
        if mo and not _is_requisite(text, m.start()):
            day = int(m.group(2)) if m.group(2) else 15
            try:
                found.append(EventDate(date(int(m.group(1)), mo, day), "day" if m.group(2) else "month", m.group(0)))
            except ValueError:
                pass
    for rx in (YEAR, YEAR_PREFIX):
        for m in rx.finditer(text):
            if not _is_requisite(text, m.start()):
                found.append(EventDate(date(int(m.group(1)), 7, 1), "year", m.group(0)))
    # самая точная из найденных; события в будущем и до принятия закона (1997) не берём
    found = [f for f in found if date(1997, 1, 1) <= f.value <= today]
    if not found:
        return None
    rank = {"day": 0, "month": 1, "year": 2}
    best = sorted(found, key=lambda f: rank[f.precision])[0]
    if best.precision == "year" and best.value.year == today.year:
        return None  # «в этом году» — действующая редакция
    return best
