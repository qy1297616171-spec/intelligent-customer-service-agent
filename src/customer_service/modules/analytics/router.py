from collections import Counter
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query

from customer_service.modules.conversation.service import InMemoryConversationStore
from customer_service.modules.handoff.service import InMemoryHandoffStore
from customer_service.modules.knowledge.service import InMemoryKnowledgeStore


def build_router(
    conversations: InMemoryConversationStore,
    handoffs: InMemoryHandoffStore,
    knowledge: InMemoryKnowledgeStore,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/analytics", tags=["数据分析"])

    @router.get("/overview")
    def overview(tenant_id: str = Query(min_length=1)) -> dict[str, object]:
        sessions = conversations.list(tenant_id)
        tickets = handoffs.list(tenant_id)
        documents = knowledge.list(tenant_id)
        messages = [message for session in sessions for message in session.messages]
        user_messages = [message for message in messages if message.role == "user"]
        assistant_messages = [message for message in messages if message.role == "assistant"]
        answer_types = Counter(
            message.answer_type or "unknown" for message in assistant_messages
        )
        resolved = answer_types["business_fact"] + answer_types["knowledge"]
        resolution_rate = round(resolved / len(user_messages) * 100, 1) if user_messages else 0
        pending = sum(session.status == "handoff" for session in sessions)

        today = datetime.now(UTC).date()
        daily = []
        for offset in range(6, -1, -1):
            day = today - timedelta(days=offset)
            daily.append(
                {
                    "date": day.strftime("%m-%d"),
                    "conversations": sum(
                        session.created_at.startswith(day.isoformat()) for session in sessions
                    ),
                    "messages": sum(
                        message.created_at.startswith(day.isoformat()) for message in messages
                    ),
                }
            )

        return {
            "metrics": {
                "conversations": len(sessions),
                "messages": len(messages),
                "resolution_rate": resolution_rate,
                "handoffs": len(tickets),
                "pending": pending,
                "knowledge": len(documents),
            },
            "answer_types": {
                "business_fact": answer_types["business_fact"],
                "knowledge": answer_types["knowledge"],
                "refusal": answer_types["refusal"],
            },
            "daily": daily,
            "recent_handoffs": [
                {
                    "ticket_no": ticket.ticket_no,
                    "customer_id": ticket.customer_id,
                    "queue": ticket.queue,
                    "priority": ticket.priority,
                    "status": ticket.status,
                    "created_at": ticket.created_at,
                }
                for ticket in sorted(tickets, key=lambda item: item.created_at, reverse=True)[:5]
            ],
        }

    return router

