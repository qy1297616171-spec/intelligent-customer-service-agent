from typing import Literal

from pydantic import BaseModel, Field


class HandoffCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    conversation_id: str = Field(min_length=1, max_length=64)
    customer_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="客户申请人工客服", min_length=1, max_length=500)


class HandoffView(BaseModel):
    id: str
    ticket_no: str
    conversation_id: str
    customer_id: str
    reason: str
    queue: str
    priority: str
    status: str
    created_at: str


class HandoffUpdate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    status: Literal["queued", "processing", "resolved", "closed"]
    priority: Literal["normal", "high"] | None = None
    queue: str | None = Field(default=None, min_length=1, max_length=100)
