import time
import hashlib
import json
from dataclasses import asdict

from redis import Redis
from redis.exceptions import RedisError

from customer_service.ai_platform.contracts import Evidence


class InMemoryAnswerCache:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._values: dict[str, tuple[float, str, list[Evidence]]] = {}

    @staticmethod
    def _key(tenant_id: str, question: str) -> str:
        return f"{tenant_id}:{' '.join(question.lower().split())}"

    def get(self, tenant_id: str, question: str) -> tuple[str, list[Evidence]] | None:
        value = self._values.get(self._key(tenant_id, question))
        if value is None:
            return None
        created_at, answer, evidence = value
        if time.monotonic() - created_at > self._ttl:
            self._values.pop(self._key(tenant_id, question), None)
            return None
        return answer, evidence

    def set(
        self, tenant_id: str, question: str, answer: str, evidence: list[Evidence]
    ) -> None:
        self._values[self._key(tenant_id, question)] = (
            time.monotonic(), answer, evidence
        )

    def invalidate_tenant(self, tenant_id: str) -> None:
        prefix = f"{tenant_id}:"
        for key in [key for key in self._values if key.startswith(prefix)]:
            self._values.pop(key, None)


class RedisAnswerCache:
    def __init__(self, client: Redis, ttl_seconds: int) -> None:
        self._client = client
        self._ttl = ttl_seconds

    def _version(self, tenant_id: str) -> int:
        value = self._client.get(f"cs:answer-version:{tenant_id}")
        return int(value or 0)

    def _key(self, tenant_id: str, question: str) -> str:
        normalized = " ".join(question.lower().split())
        version = self._version(tenant_id)
        digest = hashlib.sha256(
            f"{tenant_id}:{version}:{normalized}".encode()
        ).hexdigest()
        return f"cs:answer:{digest}"

    def get(self, tenant_id: str, question: str) -> tuple[str, list[Evidence]] | None:
        value = self._client.get(self._key(tenant_id, question))
        if not value:
            return None
        data = json.loads(value)
        return data["answer"], [Evidence(**item) for item in data["evidence"]]

    def set(self, tenant_id: str, question: str, answer: str, evidence: list[Evidence]) -> None:
        value = json.dumps(
            {"answer": answer, "evidence": [asdict(item) for item in evidence]},
            ensure_ascii=False,
        )
        self._client.set(self._key(tenant_id, question), value, ex=self._ttl)

    def invalidate_tenant(self, tenant_id: str) -> None:
        self._client.incr(f"cs:answer-version:{tenant_id}")


class ResilientAnswerCache:
    def __init__(self, primary: RedisAnswerCache, fallback: InMemoryAnswerCache) -> None:
        self._primary = primary
        self._fallback = fallback

    def get(self, tenant_id: str, question: str) -> tuple[str, list[Evidence]] | None:
        try:
            return self._primary.get(tenant_id, question) or self._fallback.get(tenant_id, question)
        except (RedisError, ValueError, TypeError, KeyError):
            return self._fallback.get(tenant_id, question)

    def set(self, tenant_id: str, question: str, answer: str, evidence: list[Evidence]) -> None:
        self._fallback.set(tenant_id, question, answer, evidence)
        try:
            self._primary.set(tenant_id, question, answer, evidence)
        except RedisError:
            pass

    def invalidate_tenant(self, tenant_id: str) -> None:
        self._fallback.invalidate_tenant(tenant_id)
        try:
            self._primary.invalidate_tenant(tenant_id)
        except RedisError:
            pass
