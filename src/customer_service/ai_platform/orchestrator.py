from dataclasses import dataclass
from time import perf_counter

from customer_service.ai_platform.contracts import (
    AnswerCache,
    AnswerGenerator,
    BusinessFactResolver,
    Evidence,
    Reranker,
    Retriever,
    SafetyPolicy,
)


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    evidence: list[Evidence]
    grounded: bool
    cache_hit: bool
    latency_ms: int
    answer_type: str


class AnswerOrchestrator:
    def __init__(
        self,
        retriever: Retriever,
        generator: AnswerGenerator,
        cache: AnswerCache,
        min_evidence_score: float,
        business_resolver: BusinessFactResolver | None = None,
        reranker: Reranker | None = None,
        candidate_limit: int = 20,
        evidence_limit: int = 5,
        safety_policy: SafetyPolicy | None = None,
    ) -> None:
        self._retriever = retriever
        self._generator = generator
        self._cache = cache
        self._min_score = min_evidence_score
        self._business_resolver = business_resolver
        self._reranker = reranker
        self._candidate_limit = candidate_limit
        self._evidence_limit = evidence_limit
        self._safety_policy = safety_policy

    def answer(
        self, tenant_id: str, question: str, customer_id: str | None = None
    ) -> AnswerResult:
        started = perf_counter()
        if self._safety_policy is not None and self._safety_policy.block_reason(question):
            return AnswerResult(
                answer="无法提供其他客户数据、系统密钥或编造业务结果，请通过正规流程查询；如需帮助请联系人工客服。",
                evidence=[],
                grounded=False,
                cache_hit=False,
                latency_ms=self._elapsed(started),
                answer_type="refusal",
            )
        if self._business_resolver is not None:
            business_fact = self._business_resolver.resolve(
                tenant_id, customer_id, question
            )
            if business_fact is not None:
                return AnswerResult(
                    business_fact.answer,
                    business_fact.evidence,
                    True,
                    False,
                    self._elapsed(started),
                    "business_fact",
                )

        cached = self._cache.get(tenant_id, question)
        if cached:
            answer, evidence = cached
            return AnswerResult(
                answer, evidence, True, True, self._elapsed(started), "knowledge"
            )

        evidence = self._retriever.search(
            tenant_id, question, limit=self._candidate_limit
        )
        qualified = [item for item in evidence if item.score >= self._min_score]
        if not qualified:
            return AnswerResult(
                answer="当前知识库中没有足够依据回答该问题，请补充信息或转人工客服。",
                evidence=[],
                grounded=False,
                cache_hit=False,
                latency_ms=self._elapsed(started),
                answer_type="refusal",
            )

        if self._reranker is not None:
            qualified = self._reranker.rerank(
                question, qualified, limit=self._evidence_limit
            )
        else:
            qualified = qualified[: self._evidence_limit]

        answer = self._generator.generate(question, qualified)
        self._cache.set(tenant_id, question, answer, qualified)
        return AnswerResult(
            answer, qualified, True, False, self._elapsed(started), "knowledge"
        )

    @staticmethod
    def _elapsed(started: float) -> int:
        return round((perf_counter() - started) * 1000)
