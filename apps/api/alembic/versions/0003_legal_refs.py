"""Граф закона: ссылки между пунктами одного акта (legal_refs).

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "legal_refs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version_id", sa.UUID(), sa.ForeignKey("act_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_unit_id", sa.UUID(), sa.ForeignKey("legal_units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_unit_id", sa.UUID(), sa.ForeignKey("legal_units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.UniqueConstraint("from_unit_id", "to_unit_id"),
    )
    op.create_index("ix_legal_refs_version_id", "legal_refs", ["version_id"])
    op.create_index("ix_legal_refs_from_unit_id", "legal_refs", ["from_unit_id"])
    op.create_index("ix_legal_refs_to_unit_id", "legal_refs", ["to_unit_id"])


def downgrade() -> None:
    op.drop_table("legal_refs")
