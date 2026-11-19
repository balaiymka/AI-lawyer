import uuid
from pathlib import Path

from app.services.rag.chunker import ActInfo, UnitRow, build_chunks
from ingest.adilet.parser import merge_languages, parse_adilet_html

FIXTURES = Path(__file__).parents[1] / "fixtures"
ACT = ActInfo("ZHO", "Закон Республики Казахстан «О жилищных отношениях»",
              "«Тұрғын үй қатынастары туралы» Қазақстан Республикасының Заңы")


def _units() -> list[UnitRow]:
    ru = parse_adilet_html((FIXTURES / "zho_ru_fragment.html").read_text(encoding="utf-8"), "ru")
    kk = parse_adilet_html((FIXTURES / "zho_kk_fragment.html").read_text(encoding="utf-8"), "kk")
    merged, _ = merge_languages(ru, kk)
    ids = {m.path: uuid.uuid4() for m in merged}
    return [
        UnitRow(id=ids[m.path], parent_id=ids.get(m.parent_path) if m.parent_path else None,
                unit_type=m.unit_type, number=m.number, path=m.path, heading_ru=m.heading_ru,
                heading_kk=m.heading_kk, text_ru=m.text_ru, text_kk=m.text_kk, is_repealed=m.is_repealed, ord=m.ord)
        for m in merged
    ]


def test_point_chunks_have_breadcrumbs_in_both_languages():
    chunks = build_chunks(_units(), ACT)
    by = {(c.path, c.lang): c for c in chunks}
    ru = by[("art42/p8", "ru")]
    assert ru.breadcrumb == (
        "Закон Республики Казахстан «О жилищных отношениях» › Глава 7. Управление объектом кондоминиума"
        " › Статья 42. Собрание › п. 8"
    )
    assert ru.content.endswith("от общего числа собственников квартир, нежилых помещений.")
    assert ru.article == "42" and ru.point == "8" and ru.kind == "point"
    kk = by[("art42/p8", "kk")]
    assert "42-бап. Жиналыс › 8-тармақ" in kk.breadcrumb
    assert "жартысынан көбі қатысса" in kk.content


def test_repealed_and_structural_units_are_not_indexed():
    paths = {c.path for c in build_chunks(_units(), ACT)}
    assert "art43" not in paths  # исключена
    assert not any(p.startswith(("ch", "sec")) for p in paths)
    # подпункты обычного (короткого) пункта входят в пункт, отдельно не индексируются
    assert "art42/p2/sp1" not in paths
    assert "art42/p2" in paths


def test_act_without_articles_chunks_points_inside_chapters():
    import uuid as _uuid

    from app.services.rag.chunker import ActInfo, UnitRow, build_chunks

    def row(path, unit_type, number, parent=None, text=None, heading=None, ord_=0):
        return UnitRow(id=_uuid.uuid4(), parent_id=parent.id if parent else None, unit_type=unit_type,
                       number=number, path=path, heading_ru=heading, heading_kk=None, text_ru=text, text_kk=None,
                       is_repealed=False, ord=ord_)

    order_p1 = row("order/p1", "point", "1", text="1. Утвердить прилагаемые Правила.", ord_=0)
    ch1 = row("ch1", "chapter", "1", heading="Общие положения", ord_=1)
    p1 = row("p1", "point", "1", parent=ch1, text="1. Настоящие Правила определяют порядок управления.", ord_=2)
    form_p1 = row("a2/p1", "point", "1", text="1. ______________", ord_=3)
    chunks = build_chunks([order_p1, ch1, p1, form_p1], ActInfo("RULES_MGMT", "Правила по управлению", None))
    assert [c.path for c in chunks] == ["p1"]
    assert chunks[0].article is None and chunks[0].point == "1"
    assert "Глава 1. Общие положения › п. 1" in chunks[0].breadcrumb
