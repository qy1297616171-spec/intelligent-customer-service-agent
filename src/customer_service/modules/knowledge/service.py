from __future__ import annotations

import re
from datetime import UTC, datetime
from dataclasses import dataclass
from threading import Lock
from uuid import uuid4

from sqlalchemy import delete as sql_delete, select

from customer_service.ai_platform.contracts import Evidence
from customer_service.ai_platform.embeddings import (
    EmbeddingProvider,
    cosine_similarity,
)
from customer_service.modules.knowledge.schemas import DocumentCreate, DocumentUpdate
from customer_service.infrastructure.database import (
    Database,
    KnowledgeEmbeddingRecord,
    KnowledgeRecord,
)
from customer_service.infrastructure.pgvector_store import PgVectorStore


@dataclass(frozen=True)
class KnowledgeDocument:
    id: str
    tenant_id: str
    title: str
    content: str
    source: str


class InMemoryKnowledgeStore:
    """Development adapter. Production can replace it without changing callers."""

    def __init__(self) -> None:
        self._documents: dict[str, KnowledgeDocument] = {}
        self._lock = Lock()

    def add(self, payload: DocumentCreate) -> KnowledgeDocument:
        document = KnowledgeDocument(id=str(uuid4()), **payload.model_dump())
        with self._lock:
            self._documents[document.id] = document
        return document

    def list(self, tenant_id: str) -> list[KnowledgeDocument]:
        return [d for d in self._documents.values() if d.tenant_id == tenant_id]

    def get(self, tenant_id: str, document_id: str) -> KnowledgeDocument | None:
        document = self._documents.get(document_id)
        if document is None or document.tenant_id != tenant_id:
            return None
        return document

    def update(
        self, document_id: str, payload: DocumentUpdate
    ) -> KnowledgeDocument | None:
        if self.get(payload.tenant_id, document_id) is None:
            return None
        document = KnowledgeDocument(id=document_id, **payload.model_dump())
        with self._lock:
            self._documents[document_id] = document
        return document

    def delete(self, tenant_id: str, document_id: str) -> bool:
        if self.get(tenant_id, document_id) is None:
            return False
        with self._lock:
            self._documents.pop(document_id, None)
        return True

    def search(self, tenant_id: str, query: str, limit: int = 5) -> list[Evidence]:
        query_tokens = self._tokens(query)
        if not query_tokens:
            return []
        results: list[Evidence] = []
        for document in self.list(tenant_id):
            document_tokens = self._tokens(f"{document.title} {document.content}")
            overlap = query_tokens & document_tokens
            score = len(overlap) / len(query_tokens)
            if score > 0:
                results.append(
                    Evidence(
                        document_id=document.id,
                        title=document.title,
                        content=document.content,
                        score=score,
                        source=document.source,
                    )
                )
        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]

    @staticmethod
    def _tokens(text: str) -> set[str]:
        lowered = text.lower()
        latin = set(re.findall(r"[a-z0-9]+", lowered))
        chinese = set(re.findall(r"[\u4e00-\u9fff]", lowered))
        return latin | chinese


class SqlKnowledgeStore(InMemoryKnowledgeStore):
    def __init__(
        self,
        database: Database,
        embedding_provider: EmbeddingProvider,
        vector_weight: float = 0.55,
        keyword_weight: float = 0.45,
        vector_index: PgVectorStore | None = None,
    ) -> None:
        self._database = database
        self._embeddings = embedding_provider
        total_weight = vector_weight + keyword_weight or 1.0
        self._vector_weight = vector_weight / total_weight
        self._keyword_weight = keyword_weight / total_weight
        self._vector_index = vector_index

    @staticmethod
    def _view(record: KnowledgeRecord) -> KnowledgeDocument:
        return KnowledgeDocument(
            id=record.id,
            tenant_id=record.tenant_id,
            title=record.title,
            content=record.content,
            source=record.source,
        )

    def add(self, payload: DocumentCreate) -> KnowledgeDocument:
        record = KnowledgeRecord(id=str(uuid4()), **payload.model_dump())
        embedding = self._embedding_record(
            record.id, record.tenant_id, f"{record.title} {record.content}"
        )
        with self._database.session_factory.begin() as session:
            session.add(record)
            session.add(embedding)
        if self._vector_index:
            self._vector_index.upsert(
                record.id, record.tenant_id, embedding.model, embedding.vector
            )
        return self._view(record)

    def list(self, tenant_id: str) -> list[KnowledgeDocument]:
        with self._database.session_factory() as session:
            records = session.scalars(
                select(KnowledgeRecord).where(KnowledgeRecord.tenant_id == tenant_id)
            ).all()
            return [self._view(record) for record in records]

    def get(self, tenant_id: str, document_id: str) -> KnowledgeDocument | None:
        with self._database.session_factory() as session:
            record = session.scalar(
                select(KnowledgeRecord).where(
                    KnowledgeRecord.id == document_id,
                    KnowledgeRecord.tenant_id == tenant_id,
                )
            )
            return self._view(record) if record else None

    def update(
        self, document_id: str, payload: DocumentUpdate
    ) -> KnowledgeDocument | None:
        with self._database.session_factory.begin() as session:
            record = session.scalar(
                select(KnowledgeRecord).where(
                    KnowledgeRecord.id == document_id,
                    KnowledgeRecord.tenant_id == payload.tenant_id,
                )
            )
            if record is None:
                return None
            record.title = payload.title
            record.content = payload.content
            record.source = payload.source
            embedding = session.get(KnowledgeEmbeddingRecord, document_id)
            new_vector = self._embeddings.embed(f"{record.title} {record.content}")
            if embedding is None:
                session.add(self._embedding_record(document_id, payload.tenant_id, f"{record.title} {record.content}"))
            else:
                embedding.vector = new_vector
                embedding.model = self._embeddings.model_name
                embedding.updated_at = datetime.now(UTC).isoformat(timespec="seconds")
            session.flush()
            result = self._view(record)
        if self._vector_index:
            self._vector_index.upsert(
                document_id, payload.tenant_id,
                self._embeddings.model_name, new_vector,
            )
        return result

    def delete(self, tenant_id: str, document_id: str) -> bool:
        if self._vector_index:
            self._vector_index.delete(document_id)
        with self._database.session_factory.begin() as session:
            record = session.scalar(
                select(KnowledgeRecord).where(
                    KnowledgeRecord.id == document_id,
                    KnowledgeRecord.tenant_id == tenant_id,
                )
            )
            if record is None:
                return False
            session.execute(sql_delete(KnowledgeEmbeddingRecord).where(KnowledgeEmbeddingRecord.document_id == document_id))
            session.delete(record)
            return True

    def search(self, tenant_id: str, query: str, limit: int = 5) -> list[Evidence]:
        query_tokens = self._tokens(query)
        if not query_tokens:
            return []
        query_vector = self._embeddings.embed(query)
        documents = self.list(tenant_id)
        with self._database.session_factory() as session:
            vectors = {
                record.document_id: record.vector
                for record in session.scalars(
                    select(KnowledgeEmbeddingRecord).where(
                        KnowledgeEmbeddingRecord.tenant_id == tenant_id
                    )
                ).all()
            }
        indexed_scores = (
            self._vector_index.search(tenant_id, query_vector, max(limit * 4, 20))
            if self._vector_index else {}
        )
        results: list[Evidence] = []
        for document in documents:
            text = f"{document.title} {document.content}"
            document_tokens = self._tokens(text)
            keyword_score = len(query_tokens & document_tokens) / len(query_tokens)
            document_vector = vectors.get(document.id) or self._embeddings.embed(text)
            vector_score = indexed_scores.get(
                document.id, cosine_similarity(query_vector, document_vector)
            )
            score = self._keyword_weight * keyword_score + self._vector_weight * vector_score
            if score > 0:
                results.append(Evidence(
                    document_id=document.id, title=document.title,
                    content=document.content, score=score, source=document.source,
                ))
        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]

    def _embedding_record(
        self, document_id: str, tenant_id: str, text: str
    ) -> KnowledgeEmbeddingRecord:
        return KnowledgeEmbeddingRecord(
            document_id=document_id,
            tenant_id=tenant_id,
            model=self._embeddings.model_name,
            vector=self._embeddings.embed(text),
            updated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )

    def backfill_embeddings(self) -> int:
        created = 0
        with self._database.session_factory.begin() as session:
            documents = session.scalars(select(KnowledgeRecord)).all()
            existing = {
                item.document_id: item
                for item in session.scalars(select(KnowledgeEmbeddingRecord)).all()
            }
            for document in documents:
                current = existing.get(document.id)
                if current is not None and current.model == self._embeddings.model_name:
                    continue
                replacement = self._embedding_record(
                    document.id,
                    document.tenant_id,
                    f"{document.title} {document.content}",
                )
                if current is None:
                    session.add(replacement)
                else:
                    current.model = replacement.model
                    current.vector = replacement.vector
                    current.updated_at = replacement.updated_at
                created += 1
        if self._vector_index:
            with self._database.session_factory() as session:
                for item in session.scalars(select(KnowledgeEmbeddingRecord)).all():
                    self._vector_index.upsert(
                        item.document_id, item.tenant_id, item.model, item.vector
                    )
        return created
