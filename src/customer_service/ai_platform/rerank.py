import re

import httpx

from customer_service.ai_platform.contracts import Evidence, Reranker


class RerankGatewayError(RuntimeError):
    pass


class HeuristicReranker:
    """Deterministic local fallback used in development and during provider outages."""

    @staticmethod
    def _tokens(text: str) -> set[str]:
        normalized = text.lower()
        tokens = set(re.findall(r"[a-z0-9]+", normalized))
        tokens.update(re.findall(r"[\u4e00-\u9fff]", normalized))
        return tokens

    def rerank(
        self, query: str, evidence: list[Evidence], limit: int = 5
    ) -> list[Evidence]:
        query_tokens = self._tokens(query)

        def score(item: Evidence) -> float:
            document_tokens = self._tokens(f"{item.title} {item.content}")
            overlap = len(query_tokens & document_tokens) / max(len(query_tokens), 1)
            return 0.55 * item.score + 0.45 * overlap

        ranked = sorted(evidence, key=score, reverse=True)[:limit]
        return [
            Evidence(
                document_id=item.document_id,
                title=item.title,
                content=item.content,
                score=round(score(item), 6),
                source=item.source,
            )
            for item in ranked
        ]


class QwenReranker:
    """DashScope qwen3-rerank HTTP adapter."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        client: httpx.Client | None = None,
    ) -> None:
        self._endpoint = f"{base_url.rstrip('/')}/reranks"
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._client = client

    def rerank(
        self, query: str, evidence: list[Evidence], limit: int = 5
    ) -> list[Evidence]:
        if not evidence:
            return []
        documents = [
            f"标题：{item.title}\n正文：{item.content}\n来源：{item.source}"
            for item in evidence
        ]
        payload = {
            "model": self._model,
            "query": query,
            "documents": documents,
            "top_n": min(limit, len(documents)),
            "instruct": "检索与电商客服问题最相关、可直接作为回答依据的文档",
        }
        try:
            if self._client is not None:
                response = self._client.post(
                    self._endpoint,
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    timeout=self._timeout,
                )
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(
                        self._endpoint,
                        json=payload,
                        headers={"Authorization": f"Bearer {self._api_key}"},
                    )
            response.raise_for_status()
            results = response.json()["results"]
            ranked: list[Evidence] = []
            for result in results:
                item = evidence[int(result["index"])]
                ranked.append(
                    Evidence(
                        document_id=item.document_id,
                        title=item.title,
                        content=item.content,
                        score=float(result["relevance_score"]),
                        source=item.source,
                    )
                )
            return ranked[:limit]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise RerankGatewayError("Rerank 模型调用失败") from exc


class ResilientReranker:
    def __init__(self, primary: Reranker, fallback: Reranker) -> None:
        self._primary = primary
        self._fallback = fallback

    def rerank(
        self, query: str, evidence: list[Evidence], limit: int = 5
    ) -> list[Evidence]:
        try:
            return self._primary.rerank(query, evidence, limit)
        except RerankGatewayError:
            return self._fallback.rerank(query, evidence, limit)


def build_reranker(settings) -> Reranker:
    fallback = HeuristicReranker()
    provider = settings.rerank_provider.strip().lower()
    if provider in {"heuristic", "local"}:
        return fallback
    if provider not in {"qwen", "dashscope"}:
        raise ValueError("RERANK_PROVIDER must be heuristic, qwen or dashscope")
    api_key = (
        settings.rerank_api_key
        or settings.embedding_api_key
        or settings.ai_model_api_key
    )
    if not api_key:
        raise ValueError("RERANK_API_KEY is required for qwen rerank")
    primary = QwenReranker(
        base_url=settings.rerank_base_url,
        api_key=api_key,
        model=settings.rerank_model,
        timeout_seconds=settings.rerank_timeout_seconds,
    )
    return ResilientReranker(primary, fallback)
