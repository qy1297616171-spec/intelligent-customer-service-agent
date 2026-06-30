from customer_service.ai_platform.embeddings import HashEmbeddingProvider, cosine_similarity
from customer_service.infrastructure.database import Database
from customer_service.modules.knowledge.schemas import DocumentCreate
from customer_service.modules.knowledge.service import SqlKnowledgeStore


def test_hash_embedding_is_normalized_and_deterministic() -> None:
    provider = HashEmbeddingProvider(128)
    first = provider.embed("退款到账时间")
    second = provider.embed("退款到账时间")
    assert first == second
    assert round(sum(value * value for value in first), 6) == 1.0
    assert cosine_similarity(first, second) == 1.0


def test_hybrid_retrieval_ranks_relevant_document_first() -> None:
    database = Database("sqlite:///:memory:")
    database.create_schema()
    store = SqlKnowledgeStore(database, HashEmbeddingProvider(128))
    relevant = store.add(DocumentCreate(
        tenant_id="tenant-a", title="退款到账时效",
        content="退款审核通过后三个工作日内原路退回。", source="售后制度",
    ))
    store.add(DocumentCreate(
        tenant_id="tenant-a", title="发票申请",
        content="订单完成后可以申请电子发票。", source="财务制度",
    ))
    results = store.search("tenant-a", "退款需要几个工作日", limit=2)
    assert results[0].document_id == relevant.id
    assert results[0].score > results[1].score
