from pathlib import Path

import pytest

from ingest.adilet.parser import merge_languages, parse_adilet_html

FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.fixture(scope="module")
def ru():
    return parse_adilet_html((FIXTURES / "zho_ru_fragment.html").read_text(encoding="utf-8"), "ru")


@pytest.fixture(scope="module")
def kk():
    return parse_adilet_html((FIXTURES / "zho_kk_fragment.html").read_text(encoding="utf-8"), "kk")


def test_structure_ru(ru):
    units = ru.by_path()
    assert units["sec1"].unit_type == "section"
    assert units["ch7"].heading == "Управление объектом кондоминиума"
    assert units["ch7/par1"].unit_type == "paragraph"
    art42 = units["art42"]
    assert art42.heading == "Собрание"
    assert art42.anchor == "z1898"
    assert [c.path for c in art42.children] == ["art42/p1", "art42/p2", "art42/p3", "art42/p7", "art42/p8"]


def test_article_attached_to_paragraph_and_chapter(ru):
    par = ru.by_path()["ch7/par1"]
    assert [c.path for c in par.children] == ["art42", "art43"]
    ch6 = ru.by_path()["ch6"]
    assert [c.path for c in ch6.children] == ["art41"]


def test_duplicate_chapter_heading_is_merged(ru):
    assert "ch7~2" not in ru.by_path()
    assert not ru.warnings


def test_points_subpoints_and_continuations(ru):
    p2 = ru.by_path()["art42/p2"]
    assert [c.path for c in p2.children] == ["art42/p2/sp1", "art42/p2/sp2"]
    # Абзац после списка подпунктов относится к пункту, а не к последнему подпункту.
    assert p2.content[-1].startswith("Результаты голосования")
    assert "Результаты голосования" not in ru.by_path()["art42/p2/sp2"].full_text
    full = p2.full_text.splitlines()
    assert full[0] == "2. Собрание может проводиться:"
    assert full[1].startswith("1) в явочном формате")
    assert full[-1].startswith("Результаты голосования")

    p3 = ru.by_path()["art42/p3"]
    assert "жилищной инспекцией." in p3.full_text


def test_one_vote_rule_text(ru):
    p7 = ru.by_path()["art42/p7"]
    assert "имеет один голос" in p7.full_text
    assert "соответствующее количество голосов" in p7.full_text


def test_notes_and_repeal(ru):
    units = ru.by_path()
    assert units["art41"].notes and "в редакции Закона РК от 26.12.2019" in units["art41"].notes[0]
    assert not units["art41"].is_repealed
    assert units["ch6-1"].is_repealed
    assert units["art43"].is_repealed
    assert not units["ch7"].is_repealed
    # Общие сноски к акту — на корне.
    assert ru.root.notes and ru.root.notes[0].startswith("Сноска. В тексте после слова")


def test_unnumbered_list_lines_stay_in_point(ru):
    p2_art41 = ru.by_path()["art41/p2"]
    assert "общедомовые инженерные системы;" in p2_art41.full_text


def test_structure_kk(kk):
    units = kk.by_path()
    assert units["sec1"].unit_type == "section"
    assert units["ch7"].heading == "Кондоминиум объектісін басқару"
    assert units["ch7/par1"].unit_type == "paragraph"
    assert units["art42"].heading == "Жиналыс"
    assert units["art42/p2/sp2"].full_text.startswith("2) осы Заңның 43 және 44-баптарында")
    assert units["art42/p2"].content[-1].startswith("Тұрғын үй қатынастары")
    assert units["art43"].is_repealed
    assert units["ch6-1"].is_repealed


def test_merge_languages(ru, kk):
    merged, warnings = merge_languages(ru, kk)
    by_path = {m.path: m for m in merged}
    p7 = by_path["art42/p7"]
    assert "один голос" in p7.text_ru
    assert "бір дауысқа ие болады" in p7.text_kk
    assert p7.parent_path == "art42"
    assert by_path["art42"].parent_path == "ch7/par1"
    assert by_path["art42"].heading_kk == "Жиналыс"
    # Порядок: родитель всегда раньше потомков.
    order = {m.path: m.ord for m in merged}
    assert all(order[m.parent_path] < m.ord for m in merged if m.parent_path)
    # Фрагменты RU и KK сняты с разными пропусками строк; пути статей и пунктов совпадают.
    assert not [w for w in warnings if w.startswith("kk-only")]


def test_unrendered_page_is_reported():
    parsed = parse_adilet_html("<html><body><div id='root'></div></body></html>", "ru")
    assert parsed.units() == []
    assert parsed.warnings


def test_real_page_edge_cases():
    """Случаи, найденные на полном тексте ЗЖО (14.11.2026)."""
    ru_html = """
    <div class="law-paragraph"><h3 class="font-bold"> Глава 2. Приобретение права</h3></div>
    <div class="law-paragraph" data-anchor-id="z24"><h3 data-toc-head=""><span class="note"> Статья 20. (Исключена Законом РК от 06.07.2007 </span><a href="#">N 278</a><span class="note"> )</span></h3></div>
    <div class="law-paragraph"><h3 data-toc-head=""><b>Статья 21. Обмен</b></h3></div>
    <div class="law-paragraph"><p> 1. Текст пункта.</p></div>
    """
    ru = parse_adilet_html(ru_html, "ru").by_path()
    assert ru["art20"].is_repealed
    assert ru["art20"].heading.startswith("(Исключена")
    assert "art21/p1" in ru

    kk_html = """
    <div class="law-paragraph" data-anchor-id="z2"><p class="text-justify"><a name="z2"></a>1-тарау. Жалпы ережелер</p></div>
    <div class="law-paragraph"><p data-toc-head=""><b>1-бап. Заңнама</b></p></div>
    <div class="law-paragraph"><p> 1. Мәтін.</p></div>
    <div class="law-paragraph"><p data-toc-head=""><b>98-2 бап. Құқықтық режимі</b></p></div>
    """
    kk = parse_adilet_html(kk_html, "kk").by_path()
    assert kk["ch1"].heading == "Жалпы ережелер"
    assert [c.path for c in kk["ch1"].children] == ["art1", "art98-2"]
    assert kk["art98-2"].heading == "Құқықтық режимі"


def test_restarted_subpoint_numbering_is_kept_silently():
    html = """
    <div class="law-paragraph"><h3><b>Статья 1. Т</b></h3></div>
    <div class="law-paragraph"><p> 3. Первый список:</p></div>
    <div class="law-paragraph"><p> 1) а;</p></div>
    <div class="law-paragraph"><p> Второй список:</p></div>
    <div class="law-paragraph"><p> 1) б.</p></div>
    """
    parsed = parse_adilet_html(html, "ru")
    paths = [u.path for u in parsed.units()]
    assert paths == ["art1", "art1/p3", "art1/p3/sp1", "art1/p3/sp1~2"]
    assert not parsed.warnings
    assert parsed.by_path()["art1/p3"].full_text.splitlines() == ["3. Первый список:", "1) а;", "Второй список:", "1) б."]
