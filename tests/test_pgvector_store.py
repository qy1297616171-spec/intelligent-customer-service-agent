from customer_service.infrastructure.database import Database
from customer_service.infrastructure.pgvector_store import PgVectorStore


def test_pgvector_store_is_disabled_for_sqlite_and_formats_vectors() -> None:
    database = Database("sqlite:///:memory:")
    store = PgVectorStore(database, 3)
    assert store.available is False
    assert store.vector_literal([0.1, -0.25, 1.0]) == "[0.1,-0.25,1]"
    assert store.search("tenant", [0.1, 0.2, 0.3], 5) == {}
