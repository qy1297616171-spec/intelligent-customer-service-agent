from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

from sqlalchemy import select

from customer_service.ai_platform.contracts import Evidence
from customer_service.infrastructure.database import (
    ConversationRecord,
    Database,
    MessageRecord,
)


def now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class ConversationMessage:
    id: str
    role: str
    content: str
    created_at: str
    answer_type: str | None = None
    citations: list[Evidence] = field(default_factory=list)


@dataclass
class ConversationSession:
    id: str
    tenant_id: str
    customer_id: str
    customer_name: str
    status: str
    preview: str
    created_at: str
    updated_at: str
    messages: list[ConversationMessage] = field(default_factory=list)


class InMemoryConversationStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ConversationSession] = {}
        self._lock = Lock()

    def create(
        self, tenant_id: str, customer_id: str, customer_name: str
    ) -> ConversationSession:
        timestamp = now_text()
        session = ConversationSession(
            id=str(uuid4()),
            tenant_id=tenant_id,
            customer_id=customer_id,
            customer_name=customer_name,
            status="open",
            preview="新会话，等待客户提问",
            created_at=timestamp,
            updated_at=timestamp,
        )
        with self._lock:
            self._sessions[session.id] = session
        return session

    def list(self, tenant_id: str, customer_id: str | None = None) -> list[ConversationSession]:
        sessions = [
            item
            for item in self._sessions.values()
            if item.tenant_id == tenant_id
            and (customer_id is None or item.customer_id == customer_id)
        ]
        return sorted(sessions, key=lambda item: item.updated_at, reverse=True)

    def get(self, tenant_id: str, session_id: str) -> ConversationSession | None:
        session = self._sessions.get(session_id)
        if session is None or session.tenant_id != tenant_id:
            return None
        return session

    def add_message(
        self,
        session: ConversationSession,
        role: str,
        content: str,
        *,
        answer_type: str | None = None,
        citations: list[Evidence] | None = None,
    ) -> ConversationMessage:
        message = ConversationMessage(
            id=str(uuid4()),
            role=role,
            content=content,
            answer_type=answer_type,
            citations=list(citations or []),
            created_at=now_text(),
        )
        with self._lock:
            session.messages.append(message)
            session.preview = content[:80]
            session.updated_at = message.created_at
        return message

    def update_status(
        self, tenant_id: str, session_id: str, status: str
    ) -> ConversationSession | None:
        session = self.get(tenant_id, session_id)
        if session is None:
            return None
        with self._lock:
            session.status = status
            session.updated_at = now_text()
        return session


class SqlConversationStore(InMemoryConversationStore):
    def __init__(self, database: Database) -> None:
        self._database = database

    @staticmethod
    def _message_view(record: MessageRecord) -> ConversationMessage:
        return ConversationMessage(
            id=record.id,
            role=record.role,
            content=record.content,
            answer_type=record.answer_type,
            citations=[Evidence(**item) for item in (record.citations or [])],
            created_at=record.created_at,
        )

    def _session_view(
        self, record: ConversationRecord, messages: list[MessageRecord]
    ) -> ConversationSession:
        return ConversationSession(
            id=record.id,
            tenant_id=record.tenant_id,
            customer_id=record.customer_id,
            customer_name=record.customer_name,
            status=record.status,
            preview=record.preview,
            created_at=record.created_at,
            updated_at=record.updated_at,
            messages=[self._message_view(message) for message in messages],
        )

    def create(
        self, tenant_id: str, customer_id: str, customer_name: str
    ) -> ConversationSession:
        timestamp = now_text()
        record = ConversationRecord(
            id=str(uuid4()),
            tenant_id=tenant_id,
            customer_id=customer_id,
            customer_name=customer_name,
            status="open",
            preview="新会话，等待客户提问",
            created_at=timestamp,
            updated_at=timestamp,
        )
        with self._database.session_factory.begin() as session:
            session.add(record)
        return self._session_view(record, [])

    def list(self, tenant_id: str, customer_id: str | None = None) -> list[ConversationSession]:
        with self._database.session_factory() as session:
            statement = select(ConversationRecord).where(
                ConversationRecord.tenant_id == tenant_id
            )
            if customer_id is not None:
                statement = statement.where(ConversationRecord.customer_id == customer_id)
            records = session.scalars(
                statement.order_by(ConversationRecord.updated_at.desc())
            ).all()
            return [
                self._session_view(
                    record,
                    list(
                        session.scalars(
                            select(MessageRecord)
                            .where(MessageRecord.conversation_id == record.id)
                            .order_by(MessageRecord.created_at)
                        ).all()
                    ),
                )
                for record in records
            ]

    def get(self, tenant_id: str, session_id: str) -> ConversationSession | None:
        with self._database.session_factory() as session:
            record = session.scalar(
                select(ConversationRecord).where(
                    ConversationRecord.id == session_id,
                    ConversationRecord.tenant_id == tenant_id,
                )
            )
            if record is None:
                return None
            message_records = list(
                session.scalars(
                    select(MessageRecord)
                    .where(MessageRecord.conversation_id == session_id)
                    .order_by(MessageRecord.created_at)
                ).all()
            )
            return self._session_view(record, message_records)

    def add_message(
        self,
        session: ConversationSession,
        role: str,
        content: str,
        *,
        answer_type: str | None = None,
        citations: list[Evidence] | None = None,
    ) -> ConversationMessage:
        timestamp = now_text()
        record = MessageRecord(
            id=str(uuid4()),
            conversation_id=session.id,
            role=role,
            content=content,
            answer_type=answer_type,
            citations=[asdict(item) for item in (citations or [])],
            created_at=timestamp,
        )
        with self._database.session_factory.begin() as database_session:
            conversation = database_session.get(ConversationRecord, session.id)
            if conversation is None:
                raise ValueError("Conversation no longer exists")
            database_session.add(record)
            conversation.preview = content[:80]
            conversation.updated_at = timestamp
        message = self._message_view(record)
        session.messages.append(message)
        session.preview = content[:80]
        session.updated_at = timestamp
        return message

    def update_status(
        self, tenant_id: str, session_id: str, status: str
    ) -> ConversationSession | None:
        with self._database.session_factory.begin() as database_session:
            record = database_session.scalar(
                select(ConversationRecord).where(
                    ConversationRecord.id == session_id,
                    ConversationRecord.tenant_id == tenant_id,
                )
            )
            if record is None:
                return None
            record.status = status
            record.updated_at = now_text()
        return self.get(tenant_id, session_id)
