from dataclasses import dataclass
from typing import Protocol

import httpx

from customer_service.ai_platform.contracts import BusinessFact, Evidence


@dataclass(frozen=True)
class OrderLine:
    sku_id: str
    product_name: str
    specification: str
    quantity: int
    unit_price: float


@dataclass(frozen=True)
class LogisticsEvent:
    occurred_at: str
    description: str


@dataclass(frozen=True)
class CommerceOrder:
    tenant_id: str
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
    lines: tuple[OrderLine, ...]
    logistics: tuple[LogisticsEvent, ...]


class CommerceStore(Protocol):
    def list_orders(self, tenant_id: str, customer_id: str) -> list[CommerceOrder]: ...
    def get_order(
        self, tenant_id: str, customer_id: str, order_no: str
    ) -> CommerceOrder | None: ...


class OmsGatewayError(RuntimeError):
    pass


class HttpCommerceStore:
    """HTTP adapter for a real OMS or the independently deployable mock OMS."""

    def __init__(
        self, base_url: str, timeout_seconds: float = 3.0,
        api_key: str = "", client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._api_key = api_key
        self._client = client

    def _get(self, path: str, params: dict[str, str]) -> httpx.Response:
        headers = {"X-OMS-API-Key": self._api_key} if self._api_key else {}
        try:
            if self._client is not None:
                response = self._client.get(
                    f"{self._base_url}{path}", params=params,
                    headers=headers, timeout=self._timeout,
                )
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.get(
                        f"{self._base_url}{path}", params=params, headers=headers
                    )
            return response
        except httpx.HTTPError as exc:
            raise OmsGatewayError("OMS 服务连接失败") from exc

    @staticmethod
    def _order(payload: dict) -> CommerceOrder:
        return CommerceOrder(
            tenant_id=payload["tenant_id"],
            order_no=payload["order_no"],
            customer_id=payload["customer_id"],
            status=payload["status"],
            status_label=payload["status_label"],
            total_amount=float(payload["total_amount"]),
            paid_at=payload["paid_at"],
            carrier=payload["carrier"],
            tracking_no=payload["tracking_no"],
            estimated_delivery=payload["estimated_delivery"],
            refund_status=payload["refund_status"],
            lines=tuple(OrderLine(**item) for item in payload["lines"]),
            logistics=tuple(LogisticsEvent(**item) for item in payload["logistics"]),
        )

    def list_orders(self, tenant_id: str, customer_id: str) -> list[CommerceOrder]:
        response = self._get(
            f"/api/orders/customers/{customer_id}", {"tenant_id": tenant_id}
        )
        try:
            response.raise_for_status()
            return [self._order(item) for item in response.json()]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise OmsGatewayError("OMS 订单列表响应无效") from exc

    def get_order(
        self, tenant_id: str, customer_id: str, order_no: str
    ) -> CommerceOrder | None:
        response = self._get(
            f"/api/orders/{order_no}",
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        if response.status_code == 404:
            return None
        try:
            response.raise_for_status()
            return self._order(response.json())
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise OmsGatewayError("OMS 订单详情响应无效") from exc


def build_commerce_store(settings) -> CommerceStore:
    provider = settings.oms_provider.strip().lower()
    if provider in {"memory", "in-memory"}:
        return InMemoryCommerceStore()
    if provider == "http":
        return HttpCommerceStore(
            settings.oms_base_url, settings.oms_timeout_seconds, settings.oms_api_key
        )
    raise ValueError("OMS_PROVIDER must be memory or http")


class InMemoryCommerceStore:
    """Development adapter; replace with the enterprise OMS/ERP connector."""

    def __init__(self) -> None:
        self._orders = (
            CommerceOrder(
                tenant_id="demo-company",
                order_no="EC202606290001",
                customer_id="customer-2846",
                status="shipped",
                status_label="运输中",
                total_amount=299.00,
                paid_at="2026-06-28 14:32",
                carrier="顺丰速运",
                tracking_no="SF1234567890",
                estimated_delivery="2026-06-30 18:00 前",
                refund_status="未申请退款",
                lines=(
                    OrderLine(
                        sku_id="SKU-10086",
                        product_name="轻盈系列真无线蓝牙耳机",
                        specification="云雾白 · 标准版",
                        quantity=1,
                        unit_price=299.00,
                    ),
                ),
                logistics=(
                    LogisticsEvent("2026-06-29 09:16", "快件已到达上海浦东集散中心"),
                    LogisticsEvent("2026-06-28 20:40", "快件已由顺丰速运揽收"),
                    LogisticsEvent("2026-06-28 18:05", "商家已发货"),
                ),
            ),
        )

    def list_orders(self, tenant_id: str, customer_id: str) -> list[CommerceOrder]:
        return [
            order
            for order in self._orders
            if order.tenant_id == tenant_id and order.customer_id == customer_id
        ]

    def get_order(
        self, tenant_id: str, customer_id: str, order_no: str
    ) -> CommerceOrder | None:
        return next(
            (
                order
                for order in self._orders
                if order.tenant_id == tenant_id
                and order.customer_id == customer_id
                and order.order_no == order_no
            ),
            None,
        )


class CommerceFactResolver:
    """Resolves live order facts without asking an LLM to invent them."""

    LOGISTICS_TERMS = ("物流", "快递", "到哪", "发货", "送达", "订单状态")
    REFUND_TERMS = ("我的退款", "退款进度", "退款状态", "退款申请")
    ORDER_TERMS = ("我的订单", "订单详情", "订单金额")

    def __init__(self, store: CommerceStore) -> None:
        self._store = store

    def resolve(
        self, tenant_id: str, customer_id: str | None, question: str
    ) -> BusinessFact | None:
        if not customer_id:
            return None
        orders = self._store.list_orders(tenant_id, customer_id)
        if not orders:
            return None
        order = orders[0]
        if any(term in question for term in self.LOGISTICS_TERMS):
            latest = order.logistics[0]
            answer = (
                f"您的订单 {order.order_no} 当前状态为“{order.status_label}”。"
                f"{latest.occurred_at}，{latest.description}。承运方为{order.carrier}，"
                f"运单号 {order.tracking_no}，预计 {order.estimated_delivery} 送达。"
            )
            return self._fact(order, "订单物流系统", answer)
        if any(term in question for term in self.REFUND_TERMS):
            answer = (
                f"订单 {order.order_no} 当前退款状态为“{order.refund_status}”。"
                "如需申请售后，请确认商品状态后发起退款申请，或转人工客服协助处理。"
            )
            return self._fact(order, "售后订单系统", answer)
        if any(term in question for term in self.ORDER_TERMS):
            products = "、".join(line.product_name for line in order.lines)
            answer = (
                f"您最近的订单号为 {order.order_no}，商品为{products}，"
                f"实付金额 ¥{order.total_amount:.2f}，当前状态为“{order.status_label}”。"
            )
            return self._fact(order, "订单管理系统", answer)
        return None

    @staticmethod
    def _fact(order: CommerceOrder, source: str, answer: str) -> BusinessFact:
        return BusinessFact(
            answer=answer,
            evidence=[
                Evidence(
                    document_id=f"order:{order.order_no}",
                    title=f"订单 {order.order_no}",
                    content=answer,
                    score=1.0,
                    source=source,
                )
            ],
        )
