from fastapi import APIRouter, HTTPException, Query

from customer_service.modules.customer.schemas import CustomerUpdate, CustomerView
from customer_service.modules.customer.service import SqlCustomerStore


def build_router(store: SqlCustomerStore) -> APIRouter:
    router = APIRouter(prefix="/api/v1/customers", tags=["客户中心"])

    @router.get("", response_model=list[CustomerView])
    def list_customers(
        tenant_id: str = Query(min_length=1), search: str | None = None
    ) -> list[CustomerView]:
        return [CustomerView.model_validate(item, from_attributes=True) for item in store.list(tenant_id, search)]

    @router.get("/{customer_id}", response_model=CustomerView)
    def get_customer(customer_id: str, tenant_id: str = Query(min_length=1)) -> CustomerView:
        customer = store.get(tenant_id, customer_id)
        if customer is None:
            raise HTTPException(status_code=404, detail="客户不存在或无权访问")
        return CustomerView.model_validate(customer, from_attributes=True)

    @router.patch("/{customer_id}", response_model=CustomerView)
    def update_customer(customer_id: str, payload: CustomerUpdate) -> CustomerView:
        customer = store.update(
            payload.tenant_id, customer_id, payload.membership, payload.tags, payload.status
        )
        if customer is None:
            raise HTTPException(status_code=404, detail="客户不存在或无权访问")
        return CustomerView.model_validate(customer, from_attributes=True)

    return router
