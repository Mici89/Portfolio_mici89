"""add chunk metadata and document processing state fields

Revision ID: 5f7b8d2a1c44
Revises: d281df2f2167
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5f7b8d2a1c44"
down_revision: Union[str, Sequence[str], None] = "d281df2f2167"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("metadata", sa.JSON(), nullable=True))
    op.add_column("documents", sa.Column("error_message", sa.String(length=1000), nullable=True))
    op.add_column(
        "documents",
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("documents", "retry_count")
    op.drop_column("documents", "error_message")
    op.drop_column("document_chunks", "metadata")
