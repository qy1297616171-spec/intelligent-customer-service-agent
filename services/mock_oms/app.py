from fastapi import FastAPI, HTTPException, Query


app = FastAPI(title="电商模拟 OMS", version="1.0.0")

ORDERS = [
    {
        "tenant_id": "demo-company", "order_no": "EC202606290001",
        "customer_id": "customer-2846", "status": "shipped", "status_label": "运输中",
        "total_amount": 299.0, "paid_at": "2026-06-28 14:32", "carrier": "顺丰速运",
        "tracking_no": "SF1234567890", "estimated_delivery": "2026-06-30 18:00 前",
        "refund_status": "未申请退款",
        "lines": [{"sku_id": "SKU-10086", "product_name": "真无线蓝牙耳机", "specification": "云雾白", "quantity": 1, "unit_price": 299.0}],
        "logistics": [{"occurred_at": "2026-06-29 09:16", "description": "快件已到达上海浦东集散中心"}],
    },
    {
        "tenant_id": "demo-company", "order_no": "EC202606250009",
        "customer_id": "customer-2846", "status": "completed", "status_label": "已签收",
        "total_amount": 89.0, "paid_at": "2026-06-25 10:20", "carrier": "京东物流",
        "tracking_no": "JD0987654321", "estimated_delivery": "已送达",
        "refund_status": "退款审核中",
        "lines": [{"sku_id": "SKU-22001", "product_name": "便携充电器", "specification": "10000mAh", "quantity": 1, "unit_price": 89.0}],
        "logistics": [{"occurred_at": "2026-06-27 16:28", "description": "本人签收"}],
    },
    {
        "tenant_id": "brand-b", "order_no": "BB202606300001",
        "customer_id": "customer-b1", "status": "paid", "status_label": "待发货",
        "total_amount": 159.0, "paid_at": "2026-06-30 08:05", "carrier": "",
        "tracking_no": "", "estimated_delivery": "2026-07-03 前",
        "refund_status": "未申请退款",
        "lines": [{"sku_id": "B-SKU-1", "product_name": "运动水杯", "specification": "黑色 1L", "quantity": 1, "unit_price": 159.0}],
        "logistics": [],
    },
]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/orders/customers/{customer_id}")
def list_orders(customer_id: str, tenant_id: str = Query(min_length=1)) -> list[dict]:
    return [order for order in ORDERS if order["tenant_id"] == tenant_id and order["customer_id"] == customer_id]


@app.get("/api/orders/{order_no}")
def get_order(order_no: str, tenant_id: str, customer_id: str) -> dict:
    order = next((item for item in ORDERS if item["tenant_id"] == tenant_id and item["customer_id"] == customer_id and item["order_no"] == order_no), None)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order
