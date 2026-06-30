from typing import Literal

from pydantic import BaseModel, Field


class CustomerView(BaseModel):
    id: str
    tenant_id: str
    name: str
    phone: str
    email: str
    membership: str
    source: str
    region: str
    total_orders: int
    total_spent: float
    tags: list[str]
    status: str
    created_at: str


class CustomerUpdate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    membership: Literal["普通会员", "银卡会员", "金卡会员", "黑金会员"] | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    status: Literal["active", "inactive", "blocked"] | None = None

