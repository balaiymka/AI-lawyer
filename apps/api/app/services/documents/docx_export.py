"""Сборка .docx из Doc: шапка справа, заголовок по центру, текст по ширине, Times New Roman 14."""

from __future__ import annotations

import io

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

from app.services.documents.templates import Doc


def to_docx(doc: Doc) -> bytes:
    d = Document()
    sec = d.sections[0]
    sec.left_margin, sec.right_margin, sec.top_margin, sec.bottom_margin = Cm(3), Cm(1.5), Cm(2), Cm(2)
    style = d.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(14)
    style.paragraph_format.space_after = Pt(0)

    def para(text: str, align=WD_ALIGN_PARAGRAPH.JUSTIFY, bold=False, indent=True, before=0):
        p = d.add_paragraph()
        p.alignment = align
        p.paragraph_format.space_before = Pt(before)
        if indent and align == WD_ALIGN_PARAGRAPH.JUSTIFY:
            p.paragraph_format.first_line_indent = Cm(1.25)
        run = p.add_run(text)
        run.bold = bold
        return p

    def head(lines: list[str]):
        for line in lines:
            p = d.add_paragraph()
            p.paragraph_format.left_indent = Cm(8.5)
            p.add_run(line)

    head(doc.to)
    if doc.to and doc.sender:
        d.add_paragraph()
    head(doc.sender)
    para(doc.title, WD_ALIGN_PARAGRAPH.CENTER, bold=True, before=18)
    d.add_paragraph()
    for b in doc.body:
        para(b)
    if doc.requests:
        para(doc.requests_intro, before=6)
        for i, r in enumerate(doc.requests, 1):
            para(f"{i}) {r}")
    if doc.attachments:
        for chunk in doc.attachments_title.split("\n\n"):
            para(chunk, before=6)
        for i, a in enumerate(doc.attachments, 1):
            para(f"{i}. {a}", indent=False)
    if doc.signature:
        d.add_paragraph()
        for s in doc.signature:
            para(s, WD_ALIGN_PARAGRAPH.LEFT)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
