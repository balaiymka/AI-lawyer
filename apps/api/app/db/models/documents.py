import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at, uuid_pk
from app.db.models.users import Lang, lang_enum


class DocTemplate(Base):
    __tablename__ = "doc_templates"
    __table_args__ = (UniqueConstraint("code", "lang"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text)  # claim_osi, flood_act, osi_protocol, lawsuit_damage …
    lang: Mapped[Lang] = mapped_column(lang_enum)
    title: Mapped[str] = mapped_column(Text)
    file_key: Mapped[str] = mapped_column(Text)
    fields_schema: Mapped[dict] = mapped_column(JSONB)
    legal_basis: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")


class GeneratedDocument(Base):
    __tablename__ = "generated_documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"))
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("doc_templates.id"))
    data: Mapped[dict] = mapped_column(JSONB)
    docx_key: Mapped[str | None] = mapped_column(Text)
    pdf_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()


class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    __table_args__ = (
        CheckConstraint("kind IN ('contract','estimate','protocol','act','other')", name="kind"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"))
    file_key: Mapped[str] = mapped_column(Text)
    mime: Mapped[str] = mapped_column(Text)
    kind: Mapped[str | None] = mapped_column(Text)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    ocr_used: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = created_at()


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = uuid_pk()
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("uploaded_files.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(Text, server_default="queued")
    summary: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at()


class ReviewFinding(Base):
    __tablename__ = "review_findings"
    __table_args__ = (CheckConstraint("severity IN ('critical','warning','info')", name="severity"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    review_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE"))
    clause_ref: Mapped[str | None] = mapped_column(Text)
    clause_text: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str | None] = mapped_column(Text)
    issue: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text)
    unit_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))


class ReferenceRate(Base):
    """Базовая ставка НБ РК, МРП, МЗП — с историей по датам."""

    __tablename__ = "reference_rates"
    __table_args__ = (UniqueConstraint("code", "valid_from"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(Text)  # NBRK_BASE_RATE, MRP, MZP
    value: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    valid_from: Mapped[date] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(Text)


class Calculation(Base):
    __tablename__ = "calculations"
    __table_args__ = (CheckConstraint("kind IN ('penalty','quorum')", name="kind"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"))
    kind: Mapped[str] = mapped_column(Text)
    input: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(Text)
    entity: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    meta: Mapped[dict | None] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentDraft(Base):
    """Документ, который AI-юрист собирает в чате: значения полей шаблона + приложенные файлы.

    attachments — [{id, slot, name, mime, size, key}], сами файлы — на диске (UPLOADS_DIR), в LLM не отправляются.
    meta — {skipped: [ключи полей, которые пользователь решил не заполнять], autofilled: [ключи из переписки]}.
    """

    __tablename__ = "document_drafts"

    id: Mapped[uuid.UUID] = uuid_pk()
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="SET NULL"))
    template_code: Mapped[str] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(Text, server_default="ru")
    values: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    meta: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    attachments: Mapped[list] = mapped_column(JSONB, server_default="[]")
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
