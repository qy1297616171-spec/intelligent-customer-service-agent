from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select

from customer_service.infrastructure.database import CustomerRecord, Database


@dataclass(frozen=True)
class CustomerProfile:
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


class SqlCustomerStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    @staticmethod
    def _view(record: CustomerRecord) -> CustomerProfile:
        return CustomerProfile(
            id=record.id,
            tenant_id=record.tenant_id,
            name=record.name,
            phone=record.phone,
            email=record.email,
            membership=record.membership,
            source=record.source,
            region=record.region,
            total_orders=record.total_orders,
            total_spent=record.total_spent,
            tags=list(record.tags or []),
            status=record.status,
            created_at=record.created_at,
        )

    def get(self, tenant_id: str, customer_id: str) -> CustomerProfile | None:
        with self._database.session_factory() as session:
            record = session.scalar(
                select(CustomerRecord).where(
                    CustomerRecord.id == customer_id,
                    CustomerRecord.tenant_id == tenant_id,
                )
            )
            return self._view(record) if record else None

    def list(
        self, tenant_id: str, search: str | None = None
    ) -> list[CustomerProfile]:
        with self._database.session_factory() as session:
            statement = select(CustomerRecord).where(CustomerRecord.tenant_id == tenant_id)
            if search:
                keyword = f"%{search}%"
                statement = statement.where(
                    or_(
                        CustomerRecord.name.like(keyword),
                        CustomerRecord.id.like(keyword),
                        CustomerRecord.phone.like(keyword),
                    )
                )
            records = session.scalars(
                statement.order_by(CustomerRecord.total_spent.desc())
            ).all()
            return [self._view(record) for record in records]

    def update(
        self,
        tenant_id: str,
        customer_id: str,
        membership: str | None,
        tags: list[str] | None,
        status: str | None,
    ) -> CustomerProfile | None:
        with self._database.session_factory.begin() as session:
            record = session.scalar(
                select(CustomerRecord).where(
                    CustomerRecord.id == customer_id,
                    CustomerRecord.tenant_id == tenant_id,
                )
            )
            if record is None:
                return None
            if membership is not None:
                record.membership = membership
            if tags is not None:
                record.tags = tags
            if status is not None:
                record.status = status
            session.flush()
            return self._view(record)

    def ensure_demo_customers(self) -> None:
        timestamp = datetime.now(UTC).isoformat(timespec="seconds")
        demo = [
            ("customer-2846", "王女士", "138****2846", "wang***@mail.com", "金卡会员", "商城官网", "上海市", 12, 3826.0, ["高复购", "售后咨询"]),
            ("customer-1024", "陈女士", "136****1024", "chen***@mail.com", "银卡会员", "微信小程序", "杭州市", 6, 1688.0, ["价格敏感", "数码爱好者"]),
            ("customer-6688", "周先生", "139****6688", "zhou***@mail.com", "普通会员", "抖音商城", "深圳市", 3, 728.0, ["新客户"]),
            ("customer-9001", "李先生", "188****9001", "li***@mail.com", "黑金会员", "商城 App", "北京市", 28, 12680.0, ["高价值", "VIP"]),
        ]
        with self._database.session_factory.begin() as session:
            for values in demo:
                customer_id = values[0]
                exists = session.scalar(
                    select(CustomerRecord.id).where(
                        CustomerRecord.id == customer_id,
                        CustomerRecord.tenant_id == "demo-company",
                    )
                )
                if exists:
                    continue
                session.add(
                    CustomerRecord(
                        id=customer_id,
                        tenant_id="demo-company",
                        name=values[1],
                        phone=values[2],
                        email=values[3],
                        membership=values[4],
                        source=values[5],
                        region=values[6],
                        total_orders=values[7],
                        total_spent=values[8],
                        tags=values[9],
                        status="active",
                        created_at=timestamp,
                    )
                )
