"""Initial enterprise customer service schema.

Revision ID: 0001_initial
Revises: None
Create Date: 2026-06-30
"""
from alembic import op

from customer_service.infrastructure.database import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # create_all is intentionally used only in this compatibility baseline so the
    # migration can adopt both a fresh database and the existing development DB.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())

