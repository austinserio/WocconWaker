"""initial panel schema

Revision ID: 001
Revises:
Create Date: 2026-05-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "source_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("mime_type", sa.String(128)),
        sa.Column("source_url", sa.String(1024)),
        sa.Column("local_path", sa.String(1024)),
        sa.Column("drive_file_id", sa.String(128)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("uploaded_by", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "pending_lexicon",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_document_id", sa.String(36), sa.ForeignKey("source_documents.id")),
        sa.Column("woccon", sa.String(512), nullable=False),
        sa.Column("english", sa.String(1024), nullable=False),
        sa.Column("pos", sa.String(64), nullable=False),
        sa.Column("pronunciation", sa.String(512)),
        sa.Column("source_url", sa.String(1024)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reviewer_notes", sa.Text()),
        sa.Column("duplicate_of_id", sa.String(36)),
        sa.Column("duplicate_score", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "pending_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_document_id", sa.String(36), sa.ForeignKey("source_documents.id")),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(1024)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reviewer_notes", sa.Text()),
        sa.Column("duplicate_of_id", sa.String(36)),
        sa.Column("duplicate_score", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "canonical_lexicon",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("woccon", sa.String(512), nullable=False),
        sa.Column("english", sa.String(1024), nullable=False),
        sa.Column("pos", sa.String(64), nullable=False),
        sa.Column("pronunciation", sa.String(512)),
        sa.Column("source", sa.String(64)),
        sa.Column("source_url", sa.String(1024)),
        sa.Column("sort_order", sa.Integer()),
        sa.Column("woccon_normalized", sa.String(512), nullable=False),
    )
    op.create_index("ix_canonical_lexicon_woccon", "canonical_lexicon", ["woccon"])
    op.create_index("ix_canonical_lexicon_woccon_normalized", "canonical_lexicon", ["woccon_normalized"])

    op.create_table(
        "canonical_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(1024)),
        sa.Column("source_document_id", sa.String(36)),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("legacy_key", sa.String(64)),
        sa.Column("content_normalized", sa.Text(), nullable=False),
    )
    op.create_index("ix_canonical_rules_category", "canonical_rules", ["category"])
    op.create_index("ix_canonical_rules_legacy_key", "canonical_rules", ["legacy_key"], unique=True)

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(36)),
        sa.Column("payload_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("canonical_rules")
    op.drop_table("canonical_lexicon")
    op.drop_table("pending_rules")
    op.drop_table("pending_lexicon")
    op.drop_table("source_documents")
    op.drop_table("users")
