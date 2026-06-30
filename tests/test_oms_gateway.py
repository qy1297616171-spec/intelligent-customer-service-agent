import httpx

from customer_service.modules.commerce.service import HttpCommerceStore


ORDER = {
    "tenant_id": "tenant-a", "order_no": "A001", "customer_id": "c1",
    "status": "shipped", "status_label": "运输中", "total_amount": 19.9,
    "paid_at": "2026-06-30", "carrier": "顺丰", "tracking_no": "SF1",
    "estimated_delivery": "明天", "refund_status": "未申请",
    "lines": [{"sku_id": "s1", "product_name": "水杯", "specification": "黑色", "quantity": 1, "unit_price": 19.9}],
    "logistics": [{"occurred_at": "2026-06-30", "description": "已揽收"}],
}


def test_http_oms_adapter_maps_order_and_enforces_query_scope() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["tenant_id"] == "tenant-a"
        return httpx.Response(200, json=[ORDER])

    store = HttpCommerceStore(
        "https://oms.example", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    orders = store.list_orders("tenant-a", "c1")

    assert orders[0].order_no == "A001"
    assert orders[0].lines[0].product_name == "水杯"


def test_http_oms_adapter_returns_none_for_missing_order() -> None:
    store = HttpCommerceStore(
        "https://oms.example",
        client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404))),
    )
    assert store.get_order("tenant-a", "c1", "missing") is None
