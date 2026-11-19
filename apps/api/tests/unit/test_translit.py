import pytest

from app.services.nlu.normalizer import normalize_heuristic
from app.services.nlu.translit import is_mostly_latin, latin_to_cyrillic


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        ("kvorum sobraniya OSI", "кворум собрания оси"),
        ("uy kenesi kansha adamnan turady", "уй кенеси канша адамнан турады"),
        ("osi protokol bermei zhatyr", "оси протокол бермей жатыр"),
        ("sosed sverhu zatopil", "сосед сверху затопил"),
    ],
)
def test_latin_to_cyrillic(src, dst):
    assert latin_to_cyrillic(src) == dst


def test_detects_latin_only_when_dominant():
    assert is_mostly_latin("korshi su basty")
    assert not is_mostly_latin("ОСИ не дает протокол, eOtinish не отвечает")


def test_heuristic_uses_cyrillic_form_for_glossary():
    nq = normalize_heuristic("osi protokol bermei zhatyr")
    queries = [q.q for q in nq.search_queries]
    assert queries[0] == "osi protokol bermei zhatyr"
    assert "оси протокол бермей жатыр" in queries
    assert any("объединение собственников имущества" in q and "копия протокола" in q for q in queries)
    assert nq.reply_lang == "kk"
