import httpx

from customer_service.ai_platform.embeddings import (
    HashEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    ResilientEmbeddingProvider,
)


def test_openai_compatible_embedding_protocol() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    provider = OpenAICompatibleEmbeddingProvider(
        base_url="https://embedding.example/v1",
        api_key="secret",
        model="embedding-model",
        dimensions=3,
        timeout_seconds=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert provider.embed("退款政策") == [0.1, 0.2, 0.3]
    assert captured["url"].endswith("/v1/embeddings")
    assert captured["authorization"] == "Bearer secret"


def test_embedding_failure_falls_back_locally() -> None:
    primary = OpenAICompatibleEmbeddingProvider(
        base_url="https://embedding.example/v1",
        api_key="secret",
        model="embedding-model",
        dimensions=64,
        timeout_seconds=1,
        client=httpx.Client(transport=httpx.MockTransport(
            lambda _: httpx.Response(503, text="unavailable")
        )),
    )
    provider = ResilientEmbeddingProvider(primary, HashEmbeddingProvider(64))
    vector = provider.embed("物流查询")
    assert len(vector) == 64
    assert any(vector)
