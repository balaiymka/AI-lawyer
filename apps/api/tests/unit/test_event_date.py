from datetime import date

import pytest

from app.services.nlu.event_date import extract_event_date

TODAY = date(2026, 11, 16)


@pytest.mark.parametrize(
    ("text", "expected", "precision"),
    [
        ("Сосед залил меня в 2020 году, акт не составили", date(2020, 7, 1), "year"),
        ("2022 жылы онлайн дауыс беру өткіздік", date(2022, 7, 1), "year"),
        ("собрание прошло 15.03.2021, протокол не дали", date(2021, 3, 15), "day"),
        ("в марте 2021 ОСИ подняло взносы", date(2021, 3, 15), "month"),
        ("2023 жылғы наурыз айында су басты", date(2023, 3, 15), "month"),
        ("затопили в 2019г.", date(2019, 7, 1), "year"),
    ],
)
def test_event_dates(text, expected, precision):
    ev = extract_event_date(text, TODAY)
    assert ev is not None and (ev.value, ev.precision) == (expected, precision)


@pytest.mark.parametrize(
    "text",
    [
        "ОСИ не даёт копию протокола",
        "по Закону от 16 апреля 1997 года № 94 что положено?",
        "в 2026 году взносы выросли",  # текущий год — действующая редакция
        "что будет в 2030 году",
    ],
)
def test_no_event_date(text):
    assert extract_event_date(text, TODAY) is None
