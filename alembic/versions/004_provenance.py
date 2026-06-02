"""provenance and bibliography

Revision ID: 004
Revises: 003
Create Date: 2026-05-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LOCATOR_COLS = [
    ("source_page", sa.Integer()),
    ("source_page_end", sa.Integer()),
    ("source_excerpt", sa.Text()),
    ("source_chunk_index", sa.Integer()),
    ("provenance_status", sa.String(16)),
]

ENTRY_TABLES = ("pending_lexicon", "pending_rules", "canonical_lexicon", "canonical_rules")


def upgrade() -> None:
    op.add_column("source_documents", sa.Column("short_title", sa.String(256), nullable=True))
    op.add_column("source_documents", sa.Column("authors", sa.Text(), nullable=True))
    op.add_column("source_documents", sa.Column("year", sa.String(16), nullable=True))
    op.add_column("source_documents", sa.Column("pub_title", sa.String(512), nullable=True))
    op.add_column("source_documents", sa.Column("container_title", sa.String(512), nullable=True))
    op.add_column("source_documents", sa.Column("publisher", sa.String(256), nullable=True))
    op.add_column("source_documents", sa.Column("place", sa.String(128), nullable=True))
    op.add_column("source_documents", sa.Column("citation_text", sa.Text(), nullable=True))
    op.add_column(
        "source_documents",
        sa.Column("is_seed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    for table in ENTRY_TABLES:
        for col_name, col_type in LOCATOR_COLS:
            op.add_column(table, sa.Column(col_name, col_type, nullable=True))

    op.add_column(
        "canonical_lexicon",
        sa.Column("source_document_id", sa.String(36), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("canonical_lexicon", "source_document_id")
    for table in ENTRY_TABLES:
        for col_name, _ in reversed(LOCATOR_COLS):
            op.drop_column(table, col_name)
    op.drop_column("source_documents", "is_seed")
    op.drop_column("source_documents", "citation_text")
    op.drop_column("source_documents", "place")
    op.drop_column("source_documents", "publisher")
    op.drop_column("source_documents", "container_title")
    op.drop_column("source_documents", "pub_title")
    op.drop_column("source_documents", "year")
    op.drop_column("source_documents", "authors")
    op.drop_column("source_documents", "short_title")
