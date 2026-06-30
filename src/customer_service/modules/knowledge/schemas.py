from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=50_000)
    source: str = Field(default="manual", max_length=500)


class DocumentView(DocumentCreate):
    id: str


class DocumentUpdate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=50_000)
    source: str = Field(default="manual", max_length=500)
