"""set embedding dimension to 1024

Revision ID: bfb3fc01fe72
Revises: 0b2ce3166171
Create Date: 2026-07-15 15:56:21.600371

"""
from typing import Sequence, Union
import pgvector.sqlalchemy
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bfb3fc01fe72'
down_revision: Union[str, Sequence[str], None] = '0b2ce3166171'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "document_chunks",
        "embedding",
        existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=None),
        type_=pgvector.sqlalchemy.vector.VECTOR(dim=1024),
        existing_nullable=True,
        postgresql_using="embedding::vector(1024)",
    )


def downgrade() -> None:
    op.alter_column(
        "document_chunks",
        "embedding",
        existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=1024),
        type_=pgvector.sqlalchemy.vector.VECTOR(dim=None),
        existing_nullable=True,
        postgresql_using="embedding::vector",
    )