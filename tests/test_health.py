from fastapi.testclient import TestClient

from customer_service.main import create_app


def test_health_and_modules() -> None:
    client = TestClient(create_app())

    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/modules").json() == [
        {"name": "auth", "version": "0.1.0"},
        {"name": "audit", "version": "0.1.0"},
        {"name": "customer", "version": "0.1.0"},
        {"name": "commerce", "version": "0.1.0"},
        {"name": "knowledge", "version": "0.1.0"},
        {"name": "conversation", "version": "0.1.0"},
        {"name": "handoff", "version": "0.1.0"},
        {"name": "analytics", "version": "0.1.0"},
    ]


def test_chinese_home_page() -> None:
    response = TestClient(create_app()).get("/")

    assert response.status_code == 200
    assert "企业智能客服" in response.text
    assert "星选商城" in response.text
    assert 'lang="zh-CN"' in response.text


def test_model_status_does_not_expose_secret() -> None:
    response = TestClient(create_app()).get("/model-status")

    assert response.status_code == 200
    assert response.json()["model"] == "grounded-mock"
    assert "api_key" not in response.json()


def test_prometheus_metrics_are_exposed() -> None:
    client = TestClient(create_app())
    client.get("/health")
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "customer_service_http_requests_total" in response.text
