from fastapi.testclient import TestClient

from customer_service.bootstrap.config import Settings
from customer_service.main import create_app


def secure_client() -> TestClient:
    settings = Settings(
        database_url="sqlite:///:memory:",
        auth_enabled=True,
        auth_jwt_secret="test-secret-that-is-longer-than-thirty-two-characters",
        auth_bootstrap_admin_email="admin@example.com",
        auth_bootstrap_admin_password="StrongPass123!",
        auth_bootstrap_admin_name="测试管理员",
    )
    return TestClient(create_app(settings))


def test_login_tenant_boundary_and_audit_log() -> None:
    client = secure_client()
    wrong = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "WrongPass123!"},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "StrongPass123!"},
    )
    me = client.get("/api/v1/auth/me")
    forbidden = client.get(
        "/api/v1/customers", params={"tenant_id": "other-company"}
    )
    updated = client.patch(
        "/api/v1/customers/customer-2846",
        json={"tenant_id": "demo-company", "tags": ["审计验证"]},
    )
    logs = client.get(
        "/api/v1/audit-logs", params={"tenant_id": "demo-company"}
    )

    assert wrong.status_code == 401
    assert login.status_code == 200
    assert login.cookies.get("access_token")
    assert me.json()["role"] == "owner"
    assert forbidden.status_code == 403
    assert updated.status_code == 200
    assert any(log["resource"].endswith("customer-2846") for log in logs.json())


def test_unauthenticated_request_is_rejected() -> None:
    client = secure_client()
    home = client.get("/", follow_redirects=False)
    login_page = client.get("/login")
    response = client.get(
        "/api/v1/customers", params={"tenant_id": "demo-company"}
    )
    assert home.status_code == 302
    assert home.headers["location"] == "/login"
    assert "登录客服工作台" in login_page.text
    assert response.status_code == 401


def test_viewer_role_is_read_only_and_cannot_access_audit() -> None:
    client = secure_client()
    client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "StrongPass123!"},
    )
    created = client.post(
        "/api/v1/auth/users",
        json={
            "tenant_id": "demo-company",
            "email": "viewer@example.com",
            "password": "ViewerPass123!",
            "display_name": "只读成员",
            "role": "viewer",
        },
    )
    client.post("/api/v1/auth/logout")
    viewer_login = client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@example.com", "password": "ViewerPass123!"},
    )
    readable = client.get(
        "/api/v1/customers", params={"tenant_id": "demo-company"}
    )
    forbidden_write = client.patch(
        "/api/v1/customers/customer-2846",
        json={"tenant_id": "demo-company", "tags": ["越权"]},
    )
    forbidden_audit = client.get(
        "/api/v1/audit-logs", params={"tenant_id": "demo-company"}
    )

    assert created.status_code == 201
    assert viewer_login.status_code == 200
    assert readable.status_code == 200
    assert forbidden_write.status_code == 403
    assert forbidden_audit.status_code == 403
