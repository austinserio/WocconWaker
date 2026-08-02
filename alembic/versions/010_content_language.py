"""content language on source documents

Separates Catawba comparative sources from Woccon primary sources so that Catawba
vocabulary can never be committed to the Woccon lexicon.

Revision ID: 010_content_language
Revises: 009_users_auth
Create Date: 2026-08-02

"""
from alembic import op
import sqlalchemy as sa

revision = "010_content_language"
down_revision = "009_users_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_documents",
        sa.Column("content_language", sa.String(16), server_default="woccon", nullable=False),
    )
    op.create_index(
        "ix_source_documents_content_language", "source_documents", ["content_language"]
    )


def downgrade() -> None:
    op.drop_index("ix_source_documents_content_language", table_name="source_documents")
    op.drop_column("source_documents", "content_language")
