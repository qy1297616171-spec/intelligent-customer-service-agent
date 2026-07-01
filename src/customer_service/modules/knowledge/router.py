from fastapi import APIRouter, HTTPException, Query, Response

from customer_service.ai_platform.contracts import AnswerCache
from customer_service.modules.knowledge.schemas import (
    DocumentCreate,
    DocumentUpdate,
    DocumentView,
)
from customer_service.modules.knowledge.service import InMemoryKnowledgeStore


def build_router(
    store: InMemoryKnowledgeStore, answer_cache: AnswerCache | None = None
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])

    @router.post("/documents", response_model=DocumentView, status_code=201)
    def create_document(payload: DocumentCreate) -> DocumentView:
        document = store.add(payload)
        if answer_cache is not None:
            answer_cache.invalidate_tenant(payload.tenant_id)
        return DocumentView.model_validate(document, from_attributes=True)

    @router.get("/documents", response_model=list[DocumentView])
    def list_documents(tenant_id: str = Query(min_length=1)) -> list[DocumentView]:
        return [
            DocumentView.model_validate(item, from_attributes=True)
            for item in store.list(tenant_id)
        ]

    @router.put("/documents/{document_id}", response_model=DocumentView)
    def update_document(
        document_id: str, payload: DocumentUpdate
    ) -> DocumentView:
        document = store.update(document_id, payload)
        if document is None:
            raise HTTPException(status_code=404, detail="知识不存在或无权访问")
        if answer_cache is not None:
            answer_cache.invalidate_tenant(payload.tenant_id)
        return DocumentView.model_validate(document, from_attributes=True)

    @router.delete("/documents/{document_id}", status_code=204)
    def delete_document(
        document_id: str, tenant_id: str = Query(min_length=1)
    ) -> Response:
        if not store.delete(tenant_id, document_id):
            raise HTTPException(status_code=404, detail="知识不存在或无权访问")
        if answer_cache is not None:
            answer_cache.invalidate_tenant(tenant_id)
        return Response(status_code=204)

    return router
