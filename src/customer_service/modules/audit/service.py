from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from customer_service.infrastructure.database import AuditRecord, Database


class AuditStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    def add(self, tenant_id: str, user_id: str, action: str, resource: str, result: str, ip: str) -> None:
        with self._database.session_factory.begin() as session:
            session.add(AuditRecord(
                id=str(uuid4()), tenant_id=tenant_id, user_id=user_id,
                action=action, resource=resource[:500], result=result,
                ip_address=ip, created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            ))

    def list(self, tenant_id: str, limit: int = 100) -> list[AuditRecord]:
        with self._database.session_factory() as session:
            return list(session.scalars(
                select(AuditRecord).where(AuditRecord.tenant_id == tenant_id)
                .order_by(AuditRecord.created_at.desc()).limit(limit)
            ).all())
