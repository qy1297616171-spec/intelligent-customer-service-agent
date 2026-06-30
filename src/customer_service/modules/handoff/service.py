from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

from sqlalchemy import select

from customer_service.infrastructure.database import Database, HandoffRecord


@dataclass(frozen=True)
class HandoffTicket:
    id: str
    ticket_no: str
    tenant_id: str
    conversation_id: str
    customer_id: str
    reason: str
    queue: str
    priority: str
    status: str
    created_at: str


class InMemoryHandoffStore:
    def __init__(self) -> None:
        self._tickets: dict[str, HandoffTicket] = {}
        self._lock = Lock()

    def create(
        self,
        tenant_id: str,
        conversation_id: str,
        customer_id: str,
        reason: str,
    ) -> HandoffTicket:
        timestamp = datetime.now(UTC)
        ticket = HandoffTicket(
            id=str(uuid4()),
            ticket_no=f"CS{timestamp.strftime('%Y%m%d%H%M%S%f')[:17]}",
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            customer_id=customer_id,
            reason=reason,
            queue="电商售后服务组",
            priority="high" if any(word in reason for word in ("投诉", "催", "异常")) else "normal",
            status="queued",
            created_at=timestamp.isoformat(timespec="seconds"),
        )
        with self._lock:
            self._tickets[ticket.id] = ticket
        return ticket

    def list(self, tenant_id: str) -> list[HandoffTicket]:
        return [ticket for ticket in self._tickets.values() if ticket.tenant_id == tenant_id]

    def update(
        self,
        tenant_id: str,
        ticket_id: str,
        status: str,
        priority: str | None = None,
        queue: str | None = None,
    ) -> HandoffTicket | None:
        ticket = self._tickets.get(ticket_id)
        if ticket is None or ticket.tenant_id != tenant_id:
            return None
        updated = replace(
            ticket,
            status=status,
            priority=priority or ticket.priority,
            queue=queue or ticket.queue,
        )
        with self._lock:
            self._tickets[ticket_id] = updated
        return updated


class SqlHandoffStore(InMemoryHandoffStore):
    def __init__(self, database: Database) -> None:
        self._database = database

    @staticmethod
    def _view(record: HandoffRecord) -> HandoffTicket:
        return HandoffTicket(
            id=record.id,
            ticket_no=record.ticket_no,
            tenant_id=record.tenant_id,
            conversation_id=record.conversation_id,
            customer_id=record.customer_id,
            reason=record.reason,
            queue=record.queue,
            priority=record.priority,
            status=record.status,
            created_at=record.created_at,
        )

    def create(
        self,
        tenant_id: str,
        conversation_id: str,
        customer_id: str,
        reason: str,
    ) -> HandoffTicket:
        timestamp = datetime.now(UTC)
        record = HandoffRecord(
            id=str(uuid4()),
            ticket_no=f"CS{timestamp.strftime('%Y%m%d%H%M%S%f')[:17]}",
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            customer_id=customer_id,
            reason=reason,
            queue="电商售后服务组",
            priority="high" if any(word in reason for word in ("投诉", "催", "异常")) else "normal",
            status="queued",
            created_at=timestamp.isoformat(timespec="seconds"),
        )
        with self._database.session_factory.begin() as session:
            session.add(record)
        return self._view(record)

    def list(self, tenant_id: str) -> list[HandoffTicket]:
        with self._database.session_factory() as session:
            records = session.scalars(
                select(HandoffRecord).where(HandoffRecord.tenant_id == tenant_id)
            ).all()
            return [self._view(record) for record in records]

    def update(
        self,
        tenant_id: str,
        ticket_id: str,
        status: str,
        priority: str | None = None,
        queue: str | None = None,
    ) -> HandoffTicket | None:
        with self._database.session_factory.begin() as session:
            record = session.scalar(
                select(HandoffRecord).where(
                    HandoffRecord.id == ticket_id,
                    HandoffRecord.tenant_id == tenant_id,
                )
            )
            if record is None:
                return None
            record.status = status
            if priority is not None:
                record.priority = priority
            if queue is not None:
                record.queue = queue
            session.flush()
            return self._view(record)
