from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from customer_service.infrastructure.database import Database


class PgVectorStore:
    def __init__(self, database: Database, dimensions: int) -> None:
        self._database = database
        self._dimensions = dimensions

    @property
    def available(self) -> bool:
        return self._database.engine.dialect.name == "postgresql"

    @staticmethod
    def vector_literal(vector: list[float]) -> str:
        return "[" + ",".join(f"{value:.10g}" for value in vector) + "]"

    def upsert(
        self, document_id: str, tenant_id: str, model: str, vector: list[float]
    ) -> None:
        if not self.available or len(vector) != self._dimensions:
            return
        try:
            with self._database.engine.begin() as connection:
                connection.execute(text("""
                INSERT INTO knowledge_vectors_pg
                    (document_id, tenant_id, model, embedding, updated_at)
                VALUES (:document_id, :tenant_id, :model,
                        CAST(:embedding AS vector), :updated_at)
                ON CONFLICT (document_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    model = EXCLUDED.model,
                    embedding = EXCLUDED.embedding,
                    updated_at = EXCLUDED.updated_at
                """), {
                    "document_id": document_id,
                    "tenant_id": tenant_id,
                    "model": model,
                    "embedding": self.vector_literal(vector),
                    "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                })
        except SQLAlchemyError:
            return

    def delete(self, document_id: str) -> None:
        if not self.available:
            return
        try:
            with self._database.engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM knowledge_vectors_pg WHERE document_id=:id"),
                    {"id": document_id},
                )
        except SQLAlchemyError:
            return

    def search(
        self, tenant_id: str, query_vector: list[float], limit: int
    ) -> dict[str, float]:
        if not self.available or len(query_vector) != self._dimensions:
            return {}
        try:
            with self._database.engine.connect() as connection:
                rows = connection.execute(text("""
                    SELECT document_id,
                           1 - (embedding <=> CAST(:embedding AS vector)) AS score
                    FROM knowledge_vectors_pg
                    WHERE tenant_id = :tenant_id
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT :limit
                """), {
                    "tenant_id": tenant_id,
                    "embedding": self.vector_literal(query_vector),
                    "limit": limit,
                }).mappings()
                return {row["document_id"]: max(0.0, float(row["score"])) for row in rows}
        except SQLAlchemyError:
            return {}
