import io
import uuid
import zipfile
from types import SimpleNamespace

import pytest

from app.services.documents import skill


def draft(code="lawsuit_damage", values=None, meta=None, attachments=None, lang="ru"):
    return SimpleNamespace(id=uuid.uuid4(), case_id=None, template_code=code, lang=lang, values=values or {},
                           meta=meta or {}, attachments=attachments or [])


def test_first_question_is_first_missing_required():
    st = skill.state(draft(values={"court": "Суд"}))
    assert st["stage"] == "fields"
    assert st["next_question"]["key"] == "applicant_name"
    assert st["next_question"]["required"] is True


def test_optional_questions_after_required_and_skippable():
    req = {f.key: "x" for f in skill.TEMPLATES["lawsuit_damage"].fields if f.required}
    st = skill.state(draft(values=req))
    assert st["stage"] == "attachments"  # обязательные поля есть, нет обязательных приложений
    assert st["next_question"]["required"] is False
    skipped = [k for k in skill.ASK_OPTIONAL]
    st = skill.state(draft(values=req, meta={"skipped": skipped}))
    assert st["next_question"] is None


def test_ready_when_required_files_present():
    req = {f.key: "x" for f in skill.TEMPLATES["protocol_copy_request"].fields if f.required}
    st = skill.state(draft("protocol_copy_request", values=req, meta={"skipped": list(skill.ASK_OPTIONAL)}))
    assert st["stage"] == "ready"


def test_kazakh_questions():
    st = skill.state(draft(lang="kk"))
    assert "сот" in st["next_question"]["question"].lower()


def test_heuristic_values_only_clear_facts():
    text = "15.10.2026 из квартиры 16 затопило мою квартиру № 12, ущерб 350 000 тг"
    v = skill.heuristic_values(text, "lawsuit_damage")
    assert v["source_apartment"] == "16"
    assert v["apartment"] == "12"
    assert v["damage_amount"] == "350000"
    assert v["incident_date"] == "2026-10-15"
    assert "applicant_name" not in v


def test_annex_built_from_uploaded_files():
    atts = [{"id": "a", "slot": "id_card", "name": "id.png", "mime": "image/png", "size": 1, "key": "a.png"},
            {"id": "b", "slot": "photos", "name": "1.png", "mime": "image/png", "size": 1, "key": "b.png"},
            {"id": "c", "slot": "photos", "name": "2.png", "mime": "image/png", "size": 1, "key": "c.png"}]
    doc = skill.build_doc(draft(attachments=atts))
    assert doc.attachments == ["копия удостоверения личности заявителя;", "фотографии (2 шт.);",
                               "копия искового заявления для ответчика."]


def test_save_file_rejects_bad_type(tmp_path, monkeypatch):
    monkeypatch.setattr(skill, "UPLOADS_DIR", tmp_path)
    with pytest.raises(ValueError):
        skill.save_file("d1", "id_card", "x.exe", "application/x-msdownload", b"MZ")
    with pytest.raises(ValueError):
        skill.save_file("d1", "unknown", "x.pdf", "application/pdf", b"%PDF")
    att = skill.save_file("d1", "id_card", "../../etc/passwd.pdf", "application/pdf", b"%PDF-1.4")
    assert (tmp_path / "d1" / att["key"]).exists()
    assert "/" not in att["name"]


def test_zip_contains_document_and_files(tmp_path, monkeypatch):
    monkeypatch.setattr(skill, "UPLOADS_DIR", tmp_path)
    d = draft()
    att = skill.save_file(d.id, "id_card", "id.pdf", "application/pdf", b"%PDF-1.4")
    d.attachments = [att]
    data, title = skill.build_zip(d)
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert names[0].endswith(".docx") and names[1].startswith("02 Удостоверение личности")
