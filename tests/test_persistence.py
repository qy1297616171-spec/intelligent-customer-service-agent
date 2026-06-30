from pathlib import Path

from fastapi.testclient import TestClient

from customer_service.bootstrap.config import Settings
from customer_service.main import create_app


def test_knowledge_and_conversations_survive_application_restart(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'service.db').as_posix()}")
    first = TestClient(create_app(settings))
    document = first.post(
        "/api/v1/knowledge/documents",
        json={
            "tenant_id": "tenant-persistent",
            "title": "持久化规则",
            "content": "服务重启后仍然存在。",
            "source": "测试制度",
        },
    ).json()
    conversation = first.post(
        "/api/v1/conversations",
        json={
            "tenant_id": "tenant-persistent",
            "customer_id": "customer-1",
            "customer_name": "测试客户",
        },
    ).json()

    second = TestClient(create_app(settings))
    documents = second.get(
        "/api/v1/knowledge/documents", params={"tenant_id": "tenant-persistent"}
    ).json()
    conversations = second.get(
        "/api/v1/conversations", params={"tenant_id": "tenant-persistent"}
    ).json()

    assert documents[0]["id"] == document["id"]
    assert conversations[0]["id"] == conversation["id"]
