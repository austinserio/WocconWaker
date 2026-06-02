"""text_extraction_method on source_documents

Revision ID: 006
Revises: 005
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "source_documents",
        sa.Column("text_extraction_method", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_documents", "text_extraction_method")
