from fastapi.testclient import TestClient

from customer_service.main import create_app


def test_customer_can_read_own_orders_but_not_other_tenant() -> None:
    client = TestClient(create_app())
    own = client.get(
        "/api/v1/commerce/customers/customer-2846/orders",
        params={"tenant_id": "demo-company"},
    )
    other = client.get(
        "/api/v1/commerce/customers/customer-2846/orders",
        params={"tenant_id": "other-company"},
    )

    assert own.status_code == 200
    assert own.json()[0]["order_no"] == "EC202606290001"
    assert other.json() == []


def test_logistics_question_uses_business_system_without_knowledge() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/conversations/ask",
        json={
            "tenant_id": "demo-company",
            "customer_id": "customer-2846",
            "question": "我的订单物流到哪了？",
        },
    )

    assert response.status_code == 200
    assert response.json()["answer_type"] == "business_fact"
    assert "SF1234567890" in response.json()["answer"]
    assert response.json()["citations"][0]["source"] == "订单物流系统"
