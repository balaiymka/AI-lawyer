from app.services.rag.xrefs import XRef, extract_xrefs


def test_same_act_with_point():
    t = "в порядке, предусмотренном пунктом 3 статьи 42 настоящего Закона, и статьей 10-2 настоящего Закона."
    assert extract_xrefs(t, "ZHO") == [XRef("ZHO", "42", "3"), XRef("ZHO", "10-2", None)]


def test_other_act_by_name():
    t = "возмещается в соответствии со статьей 917 Гражданского кодекса Республики Казахстан"
    assert extract_xrefs(t, "ZHO") == [XRef("GK_GEN", "917", None)]


def test_ambiguous_reference_skipped():
    # акт не назван — угадывать нельзя
    assert extract_xrefs("сведения, указанные в статье 5, представляются ежегодно", "ZHO") == []


def test_kazakh_same_act():
    t = "осы Заңның 42-бабының 3-тармағында көзделген тәртіппен"
    assert extract_xrefs(t, "ZHO") == [XRef("ZHO", "42", "3")]


def test_kazakh_named_act():
    t = "Қазақстан Республикасы Азаматтық кодексінің 917-бабына сәйкес"
    assert extract_xrefs(t, "ZHO") == [XRef("GK_GEN", "917", None)]


def test_reference_to_law_in_rules():
    t = "согласно пункту 8 статьи 42 Закона Республики Казахстан «О жилищных отношениях»"
    assert extract_xrefs(t, "RULES_MGMT") == [XRef("ZHO", "42", "8")]
