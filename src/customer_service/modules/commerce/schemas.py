from pydantic import BaseModel


class OrderLineView(BaseModel):
    sku_id: str
    product_name: str
    specification: str
    quantity: int
    unit_price: float


class LogisticsEventView(BaseModel):
    occurred_at: str
    description: str


class OrderView(BaseModel):
    order_no: str
    customer_id: str
    status: str
    status_label: str
    total_amount: float
    paid_at: str
    carrier: str
    tracking_no: str
    estimated_delivery: str
    refund_status: str
    lines: list[OrderLineView]
    logistics: list[LogisticsEventView]

