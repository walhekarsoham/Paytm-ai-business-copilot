from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ApiSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )


class MerchantCreate(ApiSchema):
    business_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class MerchantLogin(ApiSchema):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class MerchantRead(ApiSchema):
    id: UUID
    business_name: str
    email: EmailStr
    created_at: datetime


class AuthResponse(ApiSchema):
    access_token: str
    token_type: str = "bearer"
    merchant: MerchantRead


class ProductFields(ApiSchema):
    name: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=80)
    sku: str = Field(min_length=1, max_length=40)
    unit_price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    cost_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    stock_quantity: int = Field(ge=0, le=2_147_483_647)
    low_stock_threshold: int = Field(default=5, ge=0, le=2_147_483_647)

    @field_validator("name", "category", "sku")
    @classmethod
    def strip_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field cannot be blank.")
        return normalized

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        return value.strip().upper()


class ProductCreate(ProductFields):
    pass


class ProductUpdate(ApiSchema):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    sku: str | None = Field(default=None, min_length=1, max_length=40)
    unit_price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    cost_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    stock_quantity: int | None = Field(default=None, ge=0, le=2_147_483_647)
    low_stock_threshold: int | None = Field(default=None, ge=0, le=2_147_483_647)

    @field_validator("name", "category", "sku")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field cannot be blank.")
        return normalized

    @field_validator("sku")
    @classmethod
    def normalize_optional_sku(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None


class ProductRead(ApiSchema):
    id: UUID
    name: str
    category: str
    sku: str
    unit_price: Decimal
    cost_price: Decimal
    stock_quantity: int
    low_stock_threshold: int
    created_at: datetime
    updated_at: datetime


class TransactionItemCreate(ApiSchema):
    product_id: UUID
    quantity: int = Field(gt=0, le=1_000_000)


class TransactionCreate(ApiSchema):
    items: list[TransactionItemCreate] = Field(min_length=1, max_length=50)
    payment_method: Literal["UPI", "Cash", "Card", "Net banking"]
    customer_reference: str | None = Field(default=None, max_length=100)

    @field_validator("customer_reference")
    @classmethod
    def normalize_customer_reference(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class TransactionItemRead(ApiSchema):
    id: UUID
    product_id: UUID | None
    product_name: str
    sku: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class TransactionRead(ApiSchema):
    id: UUID
    total: Decimal
    payment_method: str
    customer_reference: str | None
    created_at: datetime
    items: list[TransactionItemRead]


class StockRestock(ApiSchema):
    quantity: int = Field(gt=0, le=2_147_483_647)
    reason: str = Field(default="Supplier restock", min_length=1, max_length=160)


class StockCount(ApiSchema):
    stock_quantity: int = Field(ge=0, le=2_147_483_647)
    reason: str = Field(default="Physical stock count", min_length=1, max_length=160)


class ThresholdUpdate(ApiSchema):
    low_stock_threshold: int = Field(ge=0, le=2_147_483_647)


class InventoryMovementRead(ApiSchema):
    id: UUID
    product_id: UUID | None
    product_name: str
    movement_type: str
    quantity: int
    reason: str
    created_at: datetime


class InventoryRead(ApiSchema):
    products: list[ProductRead]
    movements: list[InventoryMovementRead]


class CampaignRead(ApiSchema):
    id: UUID
    name: str
    channel: str
    status: str
    reach: str
    starts_at: datetime | None
    created_at: datetime


AnalyticsPeriod = Literal["7d", "30d", "12m"]


class SalesPoint(ApiSchema):
    label: str
    current: Decimal
    previous: Decimal


class TopProductSummary(ApiSchema):
    name: str
    category: str
    sold: int
    revenue: Decimal
    share: int
    tone: str
    initials: str


class InventoryAlert(ApiSchema):
    name: str
    sku: str
    stock: int
    status: str
    tone: str


class Insight(ApiSchema):
    title: str
    description: str
    tag: str
    tone: str


class DashboardRead(ApiSchema):
    period: AnalyticsPeriod
    total_sales: Decimal
    total_orders: int
    customers: int
    average_order_value: Decimal
    sales_change_percent: Decimal | None
    sales_series: list[SalesPoint]
    top_products: list[TopProductSummary]
    inventory_alerts: list[InventoryAlert]
    insights: list[Insight]