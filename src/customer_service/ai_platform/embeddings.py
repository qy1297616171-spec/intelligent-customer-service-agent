import hashlib
import math
import re
from typing import Protocol

import httpx


class EmbeddingProvider(Protocol):
    @property
    def model_name(self) -> str: ...
    def embed(self, text: str) -> list[float]: ...


class HashEmbeddingProvider:
    """Deterministic development embedding; replace without changing retrieval."""

    def __init__(self, dimensions: int = 256) -> None:
        self._dimensions = dimensions

    @property
    def model_name(self) -> str:
        return f"hash-embedding-{self._dimensions}"

    def embed(self, text: str) -> list[float]:
        normalized = text.lower().strip()
        chinese = re.findall(r"[\u4e00-\u9fff]", normalized)
        tokens = re.findall(r"[a-z0-9]+", normalized)
        tokens.extend(chinese)
        tokens.extend("".join(chinese[index:index + 2]) for index in range(len(chinese) - 1))
        vector = [0.0] * self._dimensions
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    return max(0.0, sum(a * b for a, b in zip(left, right)))


class EmbeddingGatewayError(RuntimeError):
    pass


class OpenAICompatibleEmbeddingProvider:
    def __init__(
        self, *, base_url: str, api_key: str, model: str,
        dimensions: int, timeout_seconds: float,
        client: httpx.Client | None = None,
    ) -> None:
        self._endpoint = f"{base_url.rstrip('/')}/embeddings"
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._timeout = timeout_seconds
        self._client = client

    @property
    def model_name(self) -> str:
        return f"{self._model}:{self._dimensions}"

    def embed(self, text: str) -> list[float]:
        payload = {
            "model": self._model,
            "input": text,
            "dimensions": self._dimensions,
            "encoding_format": "float",
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            if self._client is not None:
                response = self._client.post(
                    self._endpoint, json=payload, headers=headers,
                    timeout=self._timeout,
                )
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(self._endpoint, json=payload, headers=headers)
            response.raise_for_status()
            vector = response.json()["data"][0]["embedding"]
            if not isinstance(vector, list) or not vector:
                raise EmbeddingGatewayError("嵌入模型返回空向量")
            return [float(value) for value in vector]
        except EmbeddingGatewayError:
            raise
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise EmbeddingGatewayError("嵌入模型调用失败") from exc


class ResilientEmbeddingProvider:
    def __init__(
        self, primary: EmbeddingProvider, fallback: EmbeddingProvider
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def model_name(self) -> str:
        return self._primary.model_name

    def embed(self, text: str) -> list[float]:
        try:
            return self._primary.embed(text)
        except EmbeddingGatewayError:
            return self._fallback.embed(text)


def build_embedding_provider(settings) -> EmbeddingProvider:
    fallback = HashEmbeddingProvider(settings.embedding_dimensions)
    provider = settings.embedding_provider.strip().lower()
    if provider == "hash":
        return fallback
    if provider not in {"openai-compatible", "openai_compatible"}:
        raise ValueError("EMBEDDING_PROVIDER must be 'hash' or 'openai-compatible'")
    api_key = settings.embedding_api_key or settings.ai_model_api_key
    if not api_key:
        raise ValueError("EMBEDDING_API_KEY is required for a real embedding provider")
    primary = OpenAICompatibleEmbeddingProvider(
        base_url=settings.embedding_base_url,
        api_key=api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        timeout_seconds=settings.embedding_timeout_seconds,
    )
    return ResilientEmbeddingProvider(primary, fallback)
