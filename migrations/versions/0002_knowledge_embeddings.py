"""Add knowledge embedding records.

Revision ID: 0002_embeddings
Revises: 0001_initial
Create Date: 2026-06-30
"""
from alembic import op

from customer_service.infrastructure.database import Base

revision = "0002_embeddings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.tables["knowledge_embeddings"].create(
        bind=op.get_bind(), checkfirst=True
    )


def downgrade() -> None:
    Base.metadata.tables["knowledge_embeddings"].drop(
        bind=op.get_bind(), checkfirst=True
    )
