"""Конструктор документов: список шаблонов, предпросмотр и выгрузка .docx."""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services.documents.docx_export import to_docx
from app.services.documents.templates import TEMPLATES, render

router = APIRouter(prefix="/documents", tags=["documents"])


class RenderIn(BaseModel):
    code: str
    lang: Literal["ru", "kk"] = "ru"
    values: dict[str, str | int | float | None] = Field(default_factory=dict)


def _get(code: str):
    if code not in TEMPLATES:
        raise HTTPException(404, "template not found")
    return TEMPLATES[code]


@router.get("/templates")
async def templates(lang: Literal["ru", "kk"] = "ru") -> list[dict]:
    return [t.public(lang) for t in TEMPLATES.values()]


@router.get("/templates/{code}")
async def template(code: str, lang: Literal["ru", "kk"] = "ru") -> dict:
    return _get(code).public(lang)


@router.post("/render")
async def render_doc(body: RenderIn) -> dict:
    _get(body.code)
    return asdict(render(body.code, body.lang, {k: str(v) for k, v in body.values.items() if v is not None}))


@router.post("/docx")
async def render_docx(body: RenderIn) -> Response:
    t = _get(body.code)
    doc = render(body.code, body.lang, {k: str(v) for k, v in body.values.items() if v is not None})
    name = (t.title_ru if body.lang == "ru" else t.title_kk) + ".docx"
    return Response(
        to_docx(doc),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=document.docx; filename*=UTF-8''{quote(name)}"},
    )


# --- документ в чате: черновик в деле, вопросы, приложения ----------------------------------------

import uuid as _uuid  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

from fastapi import File, Form, UploadFile  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db.models import DocumentDraft  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.documents import skill  # noqa: E402


class DraftIn(BaseModel):
    code: str
    lang: Literal["ru", "kk"] = "ru"
    case_id: str | None = None
    known: dict[str, str | None] = Field(default_factory=dict)  # из профиля: ФИО, адрес, квартира, телефон


class DraftPatch(BaseModel):
    values: dict[str, str | int | float | None] = Field(default_factory=dict)
    skip: list[str] = Field(default_factory=list)
    lang: Literal["ru", "kk"] | None = None


def _uid(value: str) -> _uuid.UUID:
    try:
        return _uuid.UUID(value)
    except ValueError as e:
        raise HTTPException(404, "not found") from e


async def _draft(session, draft_id: str) -> DocumentDraft:
    d = await session.get(DocumentDraft, _uid(draft_id))
    if d is None:
        raise HTTPException(404, "draft not found")
    return d


def _clean(code: str, values: dict) -> dict[str, str]:
    keys = {f.key for f in TEMPLATES[code].fields}
    return {k: str(v).strip()[:2000] for k, v in values.items() if k in keys and v is not None and str(v).strip()}


def _touch(d: DocumentDraft) -> None:
    d.updated_at = datetime.now(timezone.utc)


@router.post("/drafts")
async def create_draft(body: DraftIn) -> dict:
    """Начать документ в деле: поля из профиля и однозначные факты из переписки заполняются сразу."""
    _get(body.code)
    from app.services.lawyer.store import load_case

    case = await load_case(body.case_id) if body.case_id else None
    if body.case_id and case is None:
        raise HTTPException(404, "case not found")
    values = _clean(body.code, body.known)
    auto: dict[str, str] = {}
    if case:
        text = "\n".join(m["text"] for m in case["messages"] if m["role"] == "user" and m.get("text"))
        auto = {k: v for k, v in skill.heuristic_values(text, body.code).items() if k not in values}
    async with SessionLocal() as s:
        d = DocumentDraft(case_id=_uid(body.case_id) if body.case_id else None, template_code=body.code,
                          lang=body.lang, values={**values, **auto},
                          meta={"autofilled": sorted(auto), "skipped": []}, attachments=[])
        s.add(d)
        await s.commit()
        await s.refresh(d)
        return skill.state(d)


@router.get("/drafts")
async def list_drafts(case_id: str) -> list[dict]:
    async with SessionLocal() as s:
        rows = (await s.scalars(select(DocumentDraft).where(DocumentDraft.case_id == _uid(case_id))
                                .order_by(DocumentDraft.created_at))).all()
        return [skill.state(d) for d in rows]


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str) -> dict:
    async with SessionLocal() as s:
        return skill.state(await _draft(s, draft_id))


@router.patch("/drafts/{draft_id}")
async def update_draft(draft_id: str, body: DraftPatch) -> dict:
    async with SessionLocal() as s:
        d = await _draft(s, draft_id)
        keys = {f.key for f in TEMPLATES[d.template_code].fields}
        values = dict(d.values or {})
        for k, v in body.values.items():
            if k not in keys:
                continue
            if v is None or not str(v).strip():
                values.pop(k, None)
            else:
                values[k] = str(v).strip()[:2000]
        meta = dict(d.meta or {})
        auto = set(meta.get("autofilled", [])) - set(body.values)  # поправленное пользователем — уже не «из переписки»
        meta["autofilled"] = sorted(auto)
        meta["skipped"] = sorted((set(meta.get("skipped", [])) | {k for k in body.skip if k in keys}) - set(values))
        d.values, d.meta = values, meta
        if body.lang:
            d.lang = body.lang
        _touch(d)
        await s.commit()
        return skill.state(d)


@router.post("/drafts/{draft_id}/autofill")
async def autofill_draft(draft_id: str) -> dict:
    """AI дочитывает переписку и заполняет пустые поля — только явно названными фактами."""
    from app.services.lawyer.store import load_case

    async with SessionLocal() as s:
        d = await _draft(s, draft_id)
        case_id, code, lang = d.case_id, d.template_code, d.lang
    case = await load_case(str(case_id)) if case_id else None
    found = await skill.llm_values(case, code, lang if lang in ("ru", "kk") else "ru")
    async with SessionLocal() as s:
        d = await _draft(s, draft_id)
        values = dict(d.values or {})
        new = {k: v for k, v in found.items() if not str(values.get(k) or "").strip()}
        values.update(new)
        meta = dict(d.meta or {})
        meta["autofilled"] = sorted(set(meta.get("autofilled", [])) | set(new))
        d.values, d.meta = values, meta
        _touch(d)
        await s.commit()
        return skill.state(d) | {"filled_now": sorted(new)}


@router.post("/drafts/{draft_id}/files")
async def upload_file(draft_id: str, slot: str = Form(...), file: UploadFile = File(...)) -> dict:
    data = await file.read(skill.MAX_FILE_BYTES + 1)
    async with SessionLocal() as s:
        d = await _draft(s, draft_id)
        atts = list(d.attachments or [])
        if len(atts) >= skill.MAX_FILES:
            raise HTTPException(400, f"не больше {skill.MAX_FILES} файлов")
        try:  # сначала проверить и сохранить новый файл — только потом убирать старый
            att = skill.save_file(d.id, slot, file.filename or "file", file.content_type or "", data)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        slot_spec = skill.SLOTS[slot]
        if not slot_spec.multiple:  # одиночный слот: новый файл заменяет старый
            skill.delete_files(d.id, [a for a in atts if a["slot"] == slot])
            atts = [a for a in atts if a["slot"] != slot]
        d.attachments = atts + [att]
        _touch(d)
        await s.commit()
        return skill.state(d)


@router.delete("/drafts/{draft_id}/files/{file_id}")
async def delete_file(draft_id: str, file_id: str) -> dict:
    async with SessionLocal() as s:
        d = await _draft(s, draft_id)
        gone = [a for a in d.attachments or [] if a["id"] == file_id]
        skill.delete_files(d.id, gone)
        d.attachments = [a for a in d.attachments or [] if a["id"] != file_id]
        _touch(d)
        await s.commit()
        return skill.state(d)


@router.get("/drafts/{draft_id}/preview")
async def preview_draft(draft_id: str) -> dict:
    async with SessionLocal() as s:
        return asdict(skill.build_doc(await _draft(s, draft_id)))


def _download(data: bytes, name: str, media: str) -> Response:
    return Response(data, media_type=media, headers={
        "Content-Disposition": f"attachment; filename=document{name[name.rfind('.'):]}; filename*=UTF-8''{quote(name)}"})


@router.get("/drafts/{draft_id}/docx")
async def draft_docx(draft_id: str) -> Response:
    async with SessionLocal() as s:
        d = await _draft(s, draft_id)
        t = TEMPLATES[d.template_code]
        return _download(to_docx(skill.build_doc(d)), (t.title_ru if d.lang == "ru" else t.title_kk) + ".docx",
                         "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@router.get("/drafts/{draft_id}/package")
async def draft_package(draft_id: str) -> Response:
    """Документ + все приложения одним архивом — можно сразу распечатать и подать."""
    async with SessionLocal() as s:
        data, title = skill.build_zip(await _draft(s, draft_id))
    return _download(data, f"{title}.zip", "application/zip")


@router.delete("/drafts/{draft_id}")
async def delete_draft(draft_id: str) -> dict:
    """Удаляет черновик и все загруженные файлы (удостоверение и т. п.) с диска."""
    async with SessionLocal() as s:
        d = await _draft(s, draft_id)
        skill.delete_files(d.id)
        await s.delete(d)
        await s.commit()
    return {"deleted": True}
