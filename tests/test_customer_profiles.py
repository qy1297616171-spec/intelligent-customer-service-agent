from fastapi.testclient import TestClient

from customer_service.main import create_app


def test_customer_profile_search_update_and_tenant_boundary() -> None:
    client = TestClient(create_app())
    customers = client.get(
        "/api/v1/customers",
        params={"tenant_id": "demo-company", "search": "王女士"},
    )
    updated = client.patch(
        "/api/v1/customers/customer-2846",
        json={
            "tenant_id": "demo-company",
            "membership": "黑金会员",
            "tags": ["高价值", "售后重点"],
        },
    )
    forbidden = client.get(
        "/api/v1/customers/customer-2846",
        params={"tenant_id": "other-company"},
    )

    assert customers.status_code == 200
    assert customers.json()[0]["total_orders"] == 12
    assert updated.json()["membership"] == "黑金会员"
    assert updated.json()["tags"] == ["高价值", "售后重点"]
    assert forbidden.status_code == 404
