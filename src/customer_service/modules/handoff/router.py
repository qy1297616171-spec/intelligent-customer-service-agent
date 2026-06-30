from fastapi import APIRouter, HTTPException, Query

from customer_service.modules.conversation.service import InMemoryConversationStore
from customer_service.modules.handoff.schemas import (
    HandoffCreate,
    HandoffUpdate,
    HandoffView,
)
from customer_service.modules.handoff.service import InMemoryHandoffStore


def build_router(
    store: InMemoryHandoffStore, conversations: InMemoryConversationStore
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/handoffs", tags=["转人工工单"])

    @router.post("", response_model=HandoffView, status_code=201)
    def create_handoff(payload: HandoffCreate) -> HandoffView:
        session = conversations.get(payload.tenant_id, payload.conversation_id)
        if session is None or session.customer_id != payload.customer_id:
            raise HTTPException(status_code=404, detail="会话不存在或客户不匹配")
        ticket = store.create(
            payload.tenant_id,
            payload.conversation_id,
            payload.customer_id,
            payload.reason,
        )
        conversations.update_status(payload.tenant_id, payload.conversation_id, "handoff")
        return HandoffView.model_validate(ticket, from_attributes=True)

    @router.get("", response_model=list[HandoffView])
    def list_handoffs(tenant_id: str = Query(min_length=1)) -> list[HandoffView]:
        return [
            HandoffView.model_validate(ticket, from_attributes=True)
            for ticket in store.list(tenant_id)
        ]

    @router.patch("/{ticket_id}", response_model=HandoffView)
    def update_handoff(ticket_id: str, payload: HandoffUpdate) -> HandoffView:
        ticket = store.update(
            payload.tenant_id,
            ticket_id,
            payload.status,
            payload.priority,
            payload.queue,
        )
        if ticket is None:
            raise HTTPException(status_code=404, detail="工单不存在或无权访问")
        if payload.status in {"resolved", "closed"}:
            conversations.update_status(
                payload.tenant_id, ticket.conversation_id, "resolved"
            )
        return HandoffView.model_validate(ticket, from_attributes=True)

    return router
