"""lexicon teaching classification

Revision ID: 003
Revises: 002
Create Date: 2026-05-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("pending_lexicon", "canonical_lexicon"):
        op.add_column(table, sa.Column("teaching_unit", sa.String(32), nullable=True))
        op.add_column(table, sa.Column("word_class", sa.String(32), nullable=True))
        op.add_column(table, sa.Column("lesson_band", sa.String(32), nullable=True))
        op.create_index(f"ix_{table}_teaching_unit", table, ["teaching_unit"])
        op.create_index(f"ix_{table}_word_class", table, ["word_class"])
        op.create_index(f"ix_{table}_lesson_band", table, ["lesson_band"])


def downgrade() -> None:
    for table in ("pending_lexicon", "canonical_lexicon"):
        op.drop_index(f"ix_{table}_lesson_band", table_name=table)
        op.drop_index(f"ix_{table}_word_class", table_name=table)
        op.drop_index(f"ix_{table}_teaching_unit", table_name=table)
        op.drop_column(table, "lesson_band")
        op.drop_column(table, "word_class")
        op.drop_column(table, "teaching_unit")
