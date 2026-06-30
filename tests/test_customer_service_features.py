from fastapi.testclient import TestClient

from customer_service.main import create_app


def test_conversation_history_and_handoff_flow() -> None:
    client = TestClient(create_app())
    session = client.post(
        "/api/v1/conversations",
        json={
            "tenant_id": "demo-company",
            "customer_id": "customer-2846",
            "customer_name": "王女士",
        },
    ).json()
    answer = client.post(
        "/api/v1/conversations/ask",
        json={
            "tenant_id": "demo-company",
            "customer_id": "customer-2846",
            "conversation_id": session["id"],
            "question": "我的订单物流到哪了？",
        },
    ).json()

    history = client.get(
        f"/api/v1/conversations/{session['id']}/messages",
        params={"tenant_id": "demo-company"},
    ).json()
    ticket = client.post(
        "/api/v1/handoffs",
        json={
            "tenant_id": "demo-company",
            "customer_id": "customer-2846",
            "conversation_id": session["id"],
            "reason": "客户催促物流，申请人工处理",
        },
    )

    assert answer["conversation_id"] == session["id"]
    assert [message["role"] for message in history] == ["user", "assistant"]
    assert ticket.status_code == 201
    assert ticket.json()["queue"] == "电商售后服务组"
    assert ticket.json()["priority"] == "high"

    sessions = client.get(
        "/api/v1/conversations", params={"tenant_id": "demo-company"}
    ).json()
    analytics = client.get(
        "/api/v1/analytics/overview", params={"tenant_id": "demo-company"}
    ).json()
    assert sessions[0]["status"] == "handoff"
    assert analytics["metrics"]["pending"] == 1
    assert analytics["answer_types"]["business_fact"] == 1

    processing = client.patch(
        f"/api/v1/handoffs/{ticket.json()['id']}",
        json={"tenant_id": "demo-company", "status": "processing"},
    )
    resolved = client.patch(
        f"/api/v1/handoffs/{ticket.json()['id']}",
        json={"tenant_id": "demo-company", "status": "resolved"},
    )
    analytics_after = client.get(
        "/api/v1/analytics/overview", params={"tenant_id": "demo-company"}
    ).json()

    assert processing.json()["status"] == "processing"
    assert resolved.json()["status"] == "resolved"
    assert analytics_after["metrics"]["pending"] == 0


def test_knowledge_can_be_updated_and_deleted_with_tenant_boundary() -> None:
    client = TestClient(create_app())
    created = client.post(
        "/api/v1/knowledge/documents",
        json={
            "tenant_id": "demo-company",
            "title": "旧规则",
            "content": "旧内容",
            "source": "旧来源",
        },
    ).json()
    forbidden = client.delete(
        f"/api/v1/knowledge/documents/{created['id']}",
        params={"tenant_id": "other-company"},
    )
    updated = client.put(
        f"/api/v1/knowledge/documents/{created['id']}",
        json={
            "tenant_id": "demo-company",
            "title": "新版退货规则",
            "content": "商品完好可在七日内申请退货。",
            "source": "售后制度 2026",
        },
    )
    deleted = client.delete(
        f"/api/v1/knowledge/documents/{created['id']}",
        params={"tenant_id": "demo-company"},
    )

    assert forbidden.status_code == 404
    assert updated.json()["title"] == "新版退货规则"
    assert deleted.status_code == 204
