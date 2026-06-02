"""extraction focus and grammar lineage

Revision ID: 008_extraction_focus
Revises: 007_vocab_base
Create Date: 2026-06-02

"""
from alembic import op
import sqlalchemy as sa

revision = "008_extraction_focus"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_documents",
        sa.Column("extraction_focus", sa.String(32), server_default="general", nullable=False),
    )
    op.add_column("source_documents", sa.Column("grammar_lineage", sa.String(32), nullable=True))
    op.add_column("pending_rules", sa.Column("grammar_lineage", sa.String(32), nullable=True))
    op.add_column("canonical_rules", sa.Column("grammar_lineage", sa.String(32), nullable=True))
    op.create_index("ix_pending_rules_grammar_lineage", "pending_rules", ["grammar_lineage"])
    op.create_index("ix_canonical_rules_grammar_lineage", "canonical_rules", ["grammar_lineage"])


def downgrade() -> None:
    op.drop_index("ix_canonical_rules_grammar_lineage", table_name="canonical_rules")
    op.drop_index("ix_pending_rules_grammar_lineage", table_name="pending_rules")
    op.drop_column("canonical_rules", "grammar_lineage")
    op.drop_column("pending_rules", "grammar_lineage")
    op.drop_column("source_documents", "grammar_lineage")
    op.drop_column("source_documents", "extraction_focus")
