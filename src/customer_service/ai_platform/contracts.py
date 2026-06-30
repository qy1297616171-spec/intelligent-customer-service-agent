from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Evidence:
    document_id: str
    title: str
    content: str
    score: float
    source: str


@dataclass(frozen=True)
class BusinessFact:
    answer: str
    evidence: list[Evidence]


class BusinessFactResolver(Protocol):
    def resolve(
        self, tenant_id: str, customer_id: str | None, question: str
    ) -> BusinessFact | None: ...


class Retriever(Protocol):
    def search(self, tenant_id: str, query: str, limit: int = 5) -> list[Evidence]: ...


class Reranker(Protocol):
    def rerank(
        self, query: str, evidence: list[Evidence], limit: int = 5
    ) -> list[Evidence]: ...


class AnswerGenerator(Protocol):
    def generate(self, question: str, evidence: list[Evidence]) -> str: ...


class AnswerCache(Protocol):
    def get(self, tenant_id: str, question: str) -> tuple[str, list[Evidence]] | None: ...
    def set(
        self, tenant_id: str, question: str, answer: str, evidence: list[Evidence]
    ) -> None: ...
