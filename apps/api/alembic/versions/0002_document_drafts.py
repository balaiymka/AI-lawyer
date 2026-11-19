"""Черновики документов из чата: значения полей и приложения (файлы на диске).

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_drafts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("case_id", sa.UUID(), sa.ForeignKey("cases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("template_code", sa.Text(), nullable=False),
        sa.Column("lang", sa.Text(), nullable=False, server_default="ru"),
        sa.Column("values", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("attachments", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_drafts_case", "document_drafts", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_document_drafts_case", table_name="document_drafts")
    op.drop_table("document_drafts")
