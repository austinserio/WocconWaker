"""vocab base linking columns

Revision ID: 007
Revises: 006
Create Date: 2026-06-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "source_documents",
        sa.Column("is_vocab_base", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "canonical_lexicon",
        sa.Column("is_base_entry", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "canonical_lexicon",
        sa.Column("base_entry_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "canonical_lexicon",
        sa.Column("base_match_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "canonical_lexicon",
        sa.Column("base_match_method", sa.String(32), nullable=True),
    )
    op.create_index("ix_canonical_lexicon_base_entry_id", "canonical_lexicon", ["base_entry_id"])
    op.add_column(
        "pending_lexicon",
        sa.Column("base_entry_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "pending_lexicon",
        sa.Column("base_match_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "pending_lexicon",
        sa.Column("base_match_method", sa.String(32), nullable=True),
    )
    op.add_column(
        "pending_lexicon",
        sa.Column("match_status", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pending_lexicon", "match_status")
    op.drop_column("pending_lexicon", "base_match_method")
    op.drop_column("pending_lexicon", "base_match_score")
    op.drop_column("pending_lexicon", "base_entry_id")
    op.drop_index("ix_canonical_lexicon_base_entry_id", table_name="canonical_lexicon")
    op.drop_column("canonical_lexicon", "base_match_method")
    op.drop_column("canonical_lexicon", "base_match_score")
    op.drop_column("canonical_lexicon", "base_entry_id")
    op.drop_column("canonical_lexicon", "is_base_entry")
    op.drop_column("source_documents", "is_vocab_base")
