import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from customer_service.ai_platform.orchestrator import AnswerOrchestrator
from customer_service.modules.conversation.schemas import (
    AskRequest,
    AskResponse,
    Citation,
    ConversationCreate,
    ConversationView,
    MessageView,
)
from customer_service.modules.conversation.service import (
    ConversationSession,
    InMemoryConversationStore,
)


def conversation_view(session: ConversationSession) -> ConversationView:
    return ConversationView(
        id=session.id,
        tenant_id=session.tenant_id,
        customer_id=session.customer_id,
        customer_name=session.customer_name,
        status=session.status,
        preview=session.preview,
        message_count=len(session.messages),
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def build_router(
    orchestrator: AnswerOrchestrator, store: InMemoryConversationStore
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/conversations", tags=["客服会话"])

    @router.post("", response_model=ConversationView, status_code=201)
    def create_conversation(payload: ConversationCreate) -> ConversationView:
        return conversation_view(
            store.create(payload.tenant_id, payload.customer_id, payload.customer_name)
        )

    @router.get("", response_model=list[ConversationView])
    def list_conversations(
        tenant_id: str = Query(min_length=1), customer_id: str | None = None
    ) -> list[ConversationView]:
        return [conversation_view(item) for item in store.list(tenant_id, customer_id)]

    @router.get("/{conversation_id}/messages", response_model=list[MessageView])
    def list_messages(
        conversation_id: str, tenant_id: str = Query(min_length=1)
    ) -> list[MessageView]:
        session = store.get(tenant_id, conversation_id)
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在或无权访问")
        return [
            MessageView(
                id=item.id,
                role=item.role,
                content=item.content,
                answer_type=item.answer_type,
                citations=[
                    Citation(
                        document_id=evidence.document_id,
                        title=evidence.title,
                        source=evidence.source,
                        score=evidence.score,
                    )
                    for evidence in item.citations
                ],
                created_at=item.created_at,
            )
            for item in session.messages
        ]

    @router.post("/ask", response_model=AskResponse)
    def ask(payload: AskRequest) -> AskResponse:
        session = (
            store.get(payload.tenant_id, payload.conversation_id)
            if payload.conversation_id
            else store.create(
                payload.tenant_id, payload.customer_id or "anonymous", "商城访客"
            )
        )
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在或无权访问")
        store.add_message(session, "user", payload.question)
        result = orchestrator.answer(
            payload.tenant_id, payload.question, payload.customer_id
        )
        store.add_message(
            session,
            "assistant",
            result.answer,
            answer_type=result.answer_type,
            citations=result.evidence,
        )
        return AskResponse(
            conversation_id=session.id,
            answer=result.answer,
            grounded=result.grounded,
            cache_hit=result.cache_hit,
            latency_ms=result.latency_ms,
            citations=[
                Citation(
                    document_id=item.document_id,
                    title=item.title,
                    source=item.source,
                    score=item.score,
                )
                for item in result.evidence
            ],
            answer_type=result.answer_type,
        )

    @router.post("/ask/stream", response_class=StreamingResponse)
    def ask_stream(payload: AskRequest) -> StreamingResponse:
        session = (
            store.get(payload.tenant_id, payload.conversation_id)
            if payload.conversation_id
            else store.create(
                payload.tenant_id, payload.customer_id or "anonymous", "商城访客"
            )
        )
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在或无权访问")
        store.add_message(session, "user", payload.question)

        def event_stream():
            yield _sse("start", {"conversation_id": session.id})
            result = orchestrator.answer(
                payload.tenant_id, payload.question, payload.customer_id
            )
            store.add_message(
                session, "assistant", result.answer,
                answer_type=result.answer_type, citations=result.evidence,
            )
            for index in range(0, len(result.answer), 8):
                yield _sse("delta", {"content": result.answer[index:index + 8]})
            yield _sse(
                "complete",
                {
                    "conversation_id": session.id,
                    "answer": result.answer,
                    "grounded": result.grounded,
                    "cache_hit": result.cache_hit,
                    "latency_ms": result.latency_ms,
                    "answer_type": result.answer_type,
                    "citations": [
                        {
                            "document_id": item.document_id,
                            "title": item.title,
                            "source": item.source,
                            "score": item.score,
                        }
                        for item in result.evidence
                    ],
                },
            )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    return router


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
