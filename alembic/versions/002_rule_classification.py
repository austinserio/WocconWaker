"""rule classification columns

Revision ID: 002
Revises: 001
Create Date: 2026-05-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("pending_rules", "canonical_rules"):
        op.add_column(table, sa.Column("grammar_domain", sa.String(32), nullable=True))
        op.add_column(table, sa.Column("pos_tag", sa.String(32), nullable=True))
        op.add_column(table, sa.Column("construction_type", sa.String(32), nullable=True))
        op.create_index(f"ix_{table}_grammar_domain", table, ["grammar_domain"])
        op.create_index(f"ix_{table}_pos_tag", table, ["pos_tag"])
        op.create_index(f"ix_{table}_construction_type", table, ["construction_type"])


def downgrade() -> None:
    for table in ("pending_rules", "canonical_rules"):
        op.drop_index(f"ix_{table}_construction_type", table_name=table)
        op.drop_index(f"ix_{table}_pos_tag", table_name=table)
        op.drop_index(f"ix_{table}_grammar_domain", table_name=table)
        op.drop_column(table, "construction_type")
        op.drop_column(table, "pos_tag")
        op.drop_column(table, "grammar_domain")
