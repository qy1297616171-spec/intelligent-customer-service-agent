"""Add PostgreSQL pgvector HNSW index.

Revision ID: 0003_pgvector
Revises: 0002_embeddings
Create Date: 2026-06-30
"""
from alembic import op

revision = "0003_pgvector"
down_revision = "0002_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_vectors_pg (
            document_id VARCHAR(64) PRIMARY KEY
                REFERENCES knowledge_documents(id) ON DELETE CASCADE,
            tenant_id VARCHAR(64) NOT NULL,
            model VARCHAR(100) NOT NULL,
            embedding vector(256) NOT NULL,
            updated_at VARCHAR(40) NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_vectors_tenant ON knowledge_vectors_pg (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_vectors_hnsw ON knowledge_vectors_pg USING hnsw (embedding vector_cosine_ops)")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TABLE IF EXISTS knowledge_vectors_pg")
