from fastapi import APIRouter, Query
from pydantic import BaseModel

from customer_service.modules.audit.service import AuditStore


class AuditView(BaseModel):
    id: str
    user_id: str
    action: str
    resource: str
    result: str
    ip_address: str
    created_at: str


def build_router(store: AuditStore) -> APIRouter:
    router = APIRouter(prefix="/api/v1/audit-logs", tags=["审计日志"])

    @router.get("", response_model=list[AuditView])
    def list_logs(tenant_id: str = Query(min_length=1), limit: int = Query(100, ge=1, le=500)) -> list[AuditView]:
        return [AuditView.model_validate(item, from_attributes=True) for item in store.list(tenant_id, limit)]

    return router

