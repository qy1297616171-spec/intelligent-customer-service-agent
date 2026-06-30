import httpx

from customer_service.ai_platform.contracts import Evidence
from customer_service.ai_platform.generation import (
    FallbackGenerator,
    GroundedMockGenerator,
    OpenAICompatibleGenerator,
)


def evidence() -> list[Evidence]:
    return [
        Evidence(
            document_id="doc-1",
            title="退款规则",
            content="退款将在三个工作日内原路退回。",
            score=0.9,
            source="售后制度",
        )
    ]


def test_openai_compatible_generator_uses_grounded_prompt() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["authorization"]
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "三个工作日内原路退回。"}}]},
        )

    generator = OpenAICompatibleGenerator(
        base_url="https://model.example/v1",
        api_key="secret-key",
        model="example-model",
        timeout_seconds=1,
        temperature=0,
        max_tokens=200,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert generator.generate("退款多久？", evidence()) == "三个工作日内原路退回。"
    assert captured["authorization"] == "Bearer secret-key"
    assert "退款将在三个工作日内原路退回" in str(captured["body"])
    assert "不得补充证据之外" in str(captured["body"])


def test_model_failure_falls_back_to_verbatim_evidence() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    primary = OpenAICompatibleGenerator(
        base_url="https://model.example/v1",
        api_key="secret-key",
        model="example-model",
        timeout_seconds=1,
        temperature=0,
        max_tokens=200,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    generator = FallbackGenerator(primary, GroundedMockGenerator())

    assert generator.generate("退款多久？", evidence()) == "退款将在三个工作日内原路退回。"
