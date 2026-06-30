import httpx

from customer_service.ai_platform.contracts import Evidence
from customer_service.ai_platform.rerank import (
    HeuristicReranker,
    QwenReranker,
    ResilientReranker,
)


def evidence(document_id: str, title: str, score: float) -> Evidence:
    return Evidence(document_id, title, f"{title}的详细说明", score, "knowledge")


def test_qwen_reranker_uses_provider_order_and_score() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = __import__("json").loads(request.content)
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.96},
                    {"index": 0, "relevance_score": 0.31},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    reranker = QwenReranker(
        base_url="https://example.com/v1",
        api_key="secret",
        model="qwen3-rerank",
        timeout_seconds=1,
        client=client,
    )
    result = reranker.rerank(
        "退款多久到账",
        [evidence("a", "发货时效", 0.8), evidence("b", "退款时效", 0.6)],
        limit=2,
    )

    assert [item.document_id for item in result] == ["b", "a"]
    assert result[0].score == 0.96
    assert captured["payload"]["top_n"] == 2
    assert captured["payload"]["model"] == "qwen3-rerank"


def test_resilient_reranker_falls_back_on_http_error() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(503))
    )
    primary = QwenReranker(
        base_url="https://example.com/v1",
        api_key="secret",
        model="qwen3-rerank",
        timeout_seconds=1,
        client=client,
    )
    reranker = ResilientReranker(primary, HeuristicReranker())

    result = reranker.rerank(
        "退款", [evidence("a", "发货", 0.9), evidence("b", "退款", 0.5)], 1
    )

    assert result[0].document_id == "b"
