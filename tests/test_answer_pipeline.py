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


def test_knowledge_update_invalidates_tenant_answer_cache() -> None:
    client = TestClient(create_app())
    created = client.post(
        "/api/v1/knowledge/documents",
        json={"tenant_id": "tenant-cache", "title": "换货时效", "content": "换货需要五天。", "source": "policy-v1"},
    ).json()
    payload = {"tenant_id": "tenant-cache", "question": "换货需要多久？"}
    assert "五天" in client.post("/api/v1/conversations/ask", json=payload).json()["answer"]
    assert client.post("/api/v1/conversations/ask", json=payload).json()["cache_hit"] is True

    client.put(
        f"/api/v1/knowledge/documents/{created['id']}",
        json={"tenant_id": "tenant-cache", "title": "换货时效", "content": "换货需要三天。", "source": "policy-v2"},
    )
    refreshed = client.post("/api/v1/conversations/ask", json=payload).json()
    assert refreshed["cache_hit"] is False
    assert "三天" in refreshed["answer"]


def test_sse_answer_stream_has_delta_complete_and_persists_message() -> None:
    client = TestClient(create_app())
    client.post(
        "/api/v1/knowledge/documents",
        json={"tenant_id": "tenant-stream", "title": "发票", "content": "电子发票可在订单详情下载。", "source": "invoice-v1"},
    )
    with client.stream(
        "POST", "/api/v1/conversations/ask/stream",
        json={"tenant_id": "tenant-stream", "question": "电子发票在哪里下载？"},
    ) as response:
        content = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: start" in content
    assert "event: delta" in content
    assert "event: complete" in content
    assert "电子发票" in content
