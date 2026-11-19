import pytest

from app.services.rag.refs import Ref, extract_refs


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("что говорит ст 42 про кворум", [Ref("42")]),
        ("ст. 42 п. 8 ЗЖО", [Ref("42", "8", act_code="ZHO")]),
        ("согласно пункту 17 статьи 42 закона о жилищных отношениях", [Ref("42", "17", act_code="ZHO")]),
        ("статья 34-1 взносы", [Ref("34-1")]),
        ("42 статья не соблюдается", [Ref("42")]),
        ("42-бап бойынша жиналыс", [Ref("42")]),
        ("42-баптың 8-тармағы", [Ref("42", "8")]),
        ("8-тармақ 42-бап", [Ref("42", "8")]),
        ("42 бап 17 тармак бойынша хаттама бермеди", [Ref("42", "17")]),
        ("статья 42, пункт 5, подпункт 12", [Ref("42", "5", "12")]),
        ("КоАП ст 333", [Ref("333", act_code="KOAP")]),
        ("statya 39 zatopil sosed", [Ref("39")]),
    ],
)
def test_extract_refs(text, expected):
    assert extract_refs(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "в 2024 году собрание прошло",
        "квартира 42, этаж 5",
        "пост 42 охраны",
        "сосед сверху затопил",
        "100 меншік иесінің 58-і қатысуда",
    ],
)
def test_no_false_refs(text):
    assert extract_refs(text) == []


import pytest

from app.services.rag.refs import extract_refs as _refs


@pytest.mark.parametrize(
    ("text", "act"),
    [
        ("статья 917 ГК РК", "GK_GEN"),
        ("ст. 917 Гражданского кодекса (Особенная часть)", "GK_SPEC"),
        ("статья 148 ГПК", "GPK"),
        ("статья 155 КоАП", "KOAP"),
        ("статья 91 АППК", "APPK"),
        ("статья 188 Уголовного кодекса", "UK"),
        ("статья 1 Конституции", "CONST"),
        ("Азаматтық процестік кодекстің 148-бабы", "GPK"),
    ],
)
def test_new_act_hints(text, act):
    refs = _refs(text)
    assert refs and refs[0].act_code == act, (text, refs)


def test_uk_abbreviation_is_management_company_not_criminal_code():
    refs = _refs("УК не делает ремонт, статья 51-5 закона о жилищных отношениях")
    assert all(r.act_code != "UK" for r in refs)
