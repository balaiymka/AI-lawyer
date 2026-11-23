"""Законодательство РК — источник истины для RAG. Qdrant строится из этих таблиц."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, uuid_pk
from app.db.models.users import Lang, lang_enum


class LegalAct(Base):
    __tablename__ = "legal_acts"
    __table_args__ = (CheckConstraint("status IN ('active','repealed')", name="status"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, unique=True)  # ZHO, KOAP, GK_GEN …
    act_type: Mapped[str] = mapped_column(Text)  # law, code, gov_decree, ministry_order …
    title_ru: Mapped[str] = mapped_column(Text)
    title_kk: Mapped[str | None] = mapped_column(Text)
    number: Mapped[str | None] = mapped_column(Text)
    adopted_at: Mapped[date | None] = mapped_column(Date)
    adilet_id: Mapped[str | None] = mapped_column(Text)
    adilet_url_ru: Mapped[str | None] = mapped_column(Text)
    adilet_url_kk: Mapped[str | None] = mapped_column(Text)
    hierarchy_level: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(Text, server_default="active")


class ActVersion(Base):
    """Редакция акта. Новая редакция появляется, когда меняется хэш исходного текста."""

    __tablename__ = "act_versions"
    __table_args__ = (
        Index("one_current_version", "act_id", unique=True, postgresql_where=text("is_current")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    act_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("legal_acts.id"))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    source_hash: Mapped[str] = mapped_column(Text)  # sha256(ru_html + kk_html)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_current: Mapped[bool] = mapped_column(Boolean, server_default="false")


class LegalUnit(Base):
    """Узел структуры: раздел → глава → параграф → статья → пункт → подпункт."""

    __tablename__ = "legal_units"
    __table_args__ = (
        CheckConstraint(
            "unit_type IN ('section','chapter','paragraph','article','point','subpoint','annex')",
            name="unit_type",
        ),
        UniqueConstraint("version_id", "path"),
        Index("ix_legal_units_tsv_ru", "tsv_ru", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("act_versions.id", ondelete="CASCADE")
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("legal_units.id"))
    unit_type: Mapped[str] = mapped_column(Text)
    number: Mapped[str | None] = mapped_column(Text)  # '42', '42-1', '3', '1)'
    path: Mapped[str] = mapped_column(Text)  # 'art42/p3/sp1' — одинаков для kk и ru
    heading_ru: Mapped[str | None] = mapped_column(Text)
    heading_kk: Mapped[str | None] = mapped_column(Text)
    text_ru: Mapped[str | None] = mapped_column(Text)
    text_kk: Mapped[str | None] = mapped_column(Text)
    notes_ru: Mapped[str | None] = mapped_column(Text)  # «Сноска. … в редакции Закона РК от …»
    notes_kk: Mapped[str | None] = mapped_column(Text)
    adilet_anchor: Mapped[str | None] = mapped_column(Text)  # 'z1898' → url#z1898
    is_repealed: Mapped[bool] = mapped_column(Boolean, server_default="false")
    ord: Mapped[int] = mapped_column(Integer)
    tsv_ru = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('russian', coalesce(heading_ru,'') || ' ' || coalesce(text_ru,''))",
            persisted=True,
        ),
    )


class LegalChunk(Base):
    """То, что индексируется в Qdrant (point id = id чанка)."""

    __tablename__ = "legal_chunks"
    __table_args__ = (UniqueConstraint("unit_id", "lang"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_units.id", ondelete="CASCADE")
    )
    lang: Mapped[Lang] = mapped_column(lang_enum)
    breadcrumb: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int | None] = mapped_column(Integer)
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LegalGlossary(Base):
    """Термины и их сленговые/искажённые варианты — для нормализатора и лексического поиска."""

    __tablename__ = "legal_glossary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term_norm_ru: Mapped[str] = mapped_column(Text)
    term_norm_kk: Mapped[str | None] = mapped_column(Text)
    variants: Mapped[list[str]] = mapped_column(ARRAY(Text))


class LegalRef(Base):
    """Ребро графа закона: пункт from_unit ссылается на пункт to_unit того же акта и той же редакции.

    kind: exception — «за исключением / кроме случаев, указанных в …», reference — обычная отсылка.
    Строится командой `python -m ingest graph` (app/services/rag/law_graph.py).
    """

    __tablename__ = "legal_refs"
    __table_args__ = (UniqueConstraint("from_unit_id", "to_unit_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("act_versions.id", ondelete="CASCADE"), index=True)
    from_unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_units.id", ondelete="CASCADE"), index=True)
    to_unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_units.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(Text)
