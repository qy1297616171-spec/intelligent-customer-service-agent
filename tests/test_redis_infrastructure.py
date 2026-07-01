from fastapi.testclient import TestClient

from customer_service.ai_platform.cache import RedisAnswerCache
from customer_service.ai_platform.contracts import Evidence
from customer_service.bootstrap.config import Settings
from customer_service.infrastructure.redis import RateLimiter
from customer_service.main import create_app


class FakePipeline:
    def __init__(self, client): self.client = client; self.key = ""
    def incr(self, key): self.key = key; return self
    def expire(self, key, seconds): return self
    def execute(self):
        self.client.values[self.key] = self.client.values.get(self.key, 0) + 1
        return [self.client.values[self.key], True]


class FakeRedis:
    def __init__(self): self.values = {}
    def get(self, key): return self.values.get(key)
    def set(self, key, value, ex=None): self.values[key] = value; return True
    def incr(self, key):
        self.values[key] = int(self.values.get(key, 0)) + 1
        return self.values[key]
    def pipeline(self): return FakePipeline(self)


def test_redis_answer_cache_round_trip() -> None:
    cache = RedisAnswerCache(FakeRedis(), 60)
    evidence = [Evidence("doc", "退款", "三日到账", 0.9, "制度")]
    cache.set("tenant", "退款多久", "三个工作日", evidence)
    answer, restored = cache.get("tenant", "退款多久")
    assert answer == "三个工作日"
    assert restored[0].document_id == "doc"
    cache.invalidate_tenant("tenant")
    assert cache.get("tenant", "退款多久") is None


def test_rate_limiter_and_api_429() -> None:
    limiter = RateLimiter(FakeRedis())
    assert limiter.allow("client", 2)[0] is True
    assert limiter.allow("client", 2)[0] is True
    assert limiter.allow("client", 2)[0] is False

    app = create_app(Settings(
        database_url="sqlite:///:memory:",
        rate_limit_enabled=True,
        rate_limit_requests_per_minute=2,
    ))
    client = TestClient(app)
    assert client.get("/api/v1/customers", params={"tenant_id": "demo-company"}).status_code == 200
    assert client.get("/api/v1/customers", params={"tenant_id": "demo-company"}).status_code == 200
    assert client.get("/api/v1/customers", params={"tenant_id": "demo-company"}).status_code == 429
