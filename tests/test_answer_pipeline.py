from fastapi.testclient import TestClient

from customer_service.main import create_app


def test_grounded_answer_then_cache_hit() -> None:
    client = TestClient(create_app())
    document = {
        "tenant_id": "tenant-a",
        "title": "退款时效",
        "content": "退款审核通过后，款项将在三个工作日内原路退回。",
        "source": "refund-policy-v1",
    }
    assert client.post("/api/v1/knowledge/documents", json=document).status_code == 201

    payload = {"tenant_id": "tenant-a", "question": "退款需要几个工作日？"}
    first = client.post("/api/v1/conversations/ask", json=payload).json()
    second = client.post("/api/v1/conversations/ask", json=payload).json()

    assert first["grounded"] is True
    assert first["citations"][0]["source"] == "refund-policy-v1"
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True


def test_refuses_when_evidence_is_missing_or_cross_tenant() -> None:
    client = TestClient(create_app())
    client.post(
        "/api/v1/knowledge/documents",
        json={
            "tenant_id": "tenant-a",
            "title": "营业时间",
            "content": "工作日九点至十八点营业。",
            "source": "hours-v1",
        },
    )

    response = client.post(
        "/api/v1/conversations/ask",
        json={"tenant_id": "tenant-b", "question": "你们几点营业？"},
    ).json()

    assert response["grounded"] is False
    assert response["citations"] == []

