"""Конструктор документов: шаблоны на двух языках, подстановка полей, ссылки только на сверенные нормы, .docx."""

import io
import re

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.main import app
from app.services.documents.templates import BLANK, TEMPLATES, render
from app.services.lawyer.schema import AVAILABLE_TEMPLATES

VERIFIED = {"39": {"4"}, "42": {"17"}, "46": {"1"}, "10-9": {"3"}}


def test_templates_match_lawyer_schema():
    assert set(TEMPLATES) == set(AVAILABLE_TEMPLATES)


@pytest.mark.parametrize("code", list(TEMPLATES))
@pytest.mark.parametrize("lang", ["ru", "kk"])
def test_render_empty_form_uses_blanks(code, lang):
    doc = render(code, lang, {})
    text = " ".join([doc.title, *doc.to, *doc.sender, *doc.body, *doc.requests, *doc.attachments])
    assert BLANK in text
    assert "{" not in text and "None" not in text


@pytest.mark.parametrize("code", list(TEMPLATES))
def test_only_verified_norms_are_cited(code):
    for lang in ("ru", "kk"):
        doc = render(code, lang, {})
        text = " ".join([*doc.body, *doc.requests, doc.note])
        ru = re.findall(r"пункт\w* (\d+) стать\w* ([\d-]+)", text) + re.findall(r"ст\. ([\d-]+) п\. (\d+)", text)
        kk = re.findall(r"([\d-]+)-бабы\w* (\d+)-тармағ", text)
        pairs = [(a, p) for p, a in re.findall(r"пункт\w* (\d+) стать\w* ([\d-]+)", text)]
        pairs += re.findall(r"ст\. ([\d-]+) п\. (\d+)", text) + kk
        for art, point in pairs:
            assert point in VERIFIED.get(art, set()), (code, lang, art, point)
        assert ru or kk or code in {"claim_neighbor", "lawsuit_damage"}


def test_values_are_substituted():
    doc = render("protocol_copy_request", "ru", {"applicant_name": "Иванов И.И.", "apartment": "12",
                                                 "meeting_date": "2026-10-05", "osi_name": "ОСИ «Достык 5»"})
    assert "05.10.2026" in doc.requests[0]
    assert doc.sender[0] == "от Иванов И.И.,"
    assert doc.to[0] == "Председателю ОСИ «Достык 5»"


def test_api_templates_render_and_docx():
    client = TestClient(app)
    items = client.get("/v1/documents/templates", params={"lang": "kk"}).json()
    assert len(items) == 6 and items[0]["fields"][0]["label"]
    r = client.post("/v1/documents/render", json={"code": "flood_act", "lang": "kk", "values": {"apartment": "7"}})
    assert r.status_code == 200 and "№ 7" in " ".join(r.json()["body"])
    r = client.post("/v1/documents/docx", json={"code": "complaint_housing_inspection", "lang": "ru",
                                                "values": {"violation": "report", "city": "г. Алматы"}})
    assert r.status_code == 200
    text = "\n".join(p.text for p in Document(io.BytesIO(r.content)).paragraphs)
    assert "ЖАЛОБА" in text and "пункт 1 статьи 46" in text and "г. Алматы" in text
    assert client.post("/v1/documents/render", json={"code": "nope"}).status_code == 404


@pytest.mark.parametrize("lang,word", [("ru", "электронную почту"), ("kk", "электрондық поштама")])
def test_delivery_phrase_follows_document_language(lang, word):
    for code in ("protocol_copy_request", "osi_report_request"):
        doc = render(code, lang, {"delivery": "email"})
        assert word in doc.requests[-1]
        assert BLANK not in doc.requests[-1]
