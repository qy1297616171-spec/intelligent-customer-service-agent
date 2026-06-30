from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    customer_id: str | None = Field(default=None, max_length=64)
    conversation_id: str | None = Field(default=None, max_length=64)
    question: str = Field(min_length=1, max_length=4_000)


class Citation(BaseModel):
    document_id: str
    title: str
    source: str
    score: float


class AskResponse(BaseModel):
    conversation_id: str
    answer: str
    grounded: bool
    cache_hit: bool
    latency_ms: int
    citations: list[Citation]
    answer_type: str


class ConversationCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    customer_id: str = Field(min_length=1, max_length=64)
    customer_name: str = Field(default="商城访客", min_length=1, max_length=100)


class ConversationView(BaseModel):
    id: str
    tenant_id: str
    customer_id: str
    customer_name: str
    status: str
    preview: str
    message_count: int
    created_at: str
    updated_at: str


class MessageView(BaseModel):
    id: str
    role: str
    content: str
    answer_type: str | None
    citations: list[Citation]
    created_at: str
