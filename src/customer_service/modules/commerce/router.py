from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query

from customer_service.modules.commerce.schemas import OrderView
from customer_service.modules.commerce.service import CommerceStore


def build_router(store: CommerceStore) -> APIRouter:
    router = APIRouter(prefix="/api/v1/commerce", tags=["电商订单"])

    @router.get("/customers/{customer_id}/orders", response_model=list[OrderView])
    def list_orders(
        customer_id: str, tenant_id: str = Query(min_length=1)
    ) -> list[OrderView]:
        return [OrderView.model_validate(asdict(order)) for order in store.list_orders(tenant_id, customer_id)]

    @router.get("/orders/{order_no}", response_model=OrderView)
    def get_order(
        order_no: str,
        tenant_id: str = Query(min_length=1),
        customer_id: str = Query(min_length=1),
    ) -> OrderView:
        order = store.get_order(tenant_id, customer_id, order_no)
        if order is None:
            raise HTTPException(status_code=404, detail="订单不存在或无权访问")
        return OrderView.model_validate(asdict(order))

    return router
