from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas import ApiSchema


class MerchantContextInfo(ApiSchema):
    id: UUID
    business_name: str
    merchant_type: str
    merchant_type_source: str


class SalesMetric(ApiSchema):
    sales: Decimal
    transactions: int
    unique_customer_references: int
    average_order_value: Decimal


class DailySales(ApiSchema):
    day: datetime
    sales: Decimal
    transactions: int


class PeriodSalesTrend(ApiSchema):
    period: Literal["daily", "weekly", "monthly"]
    current_revenue: Decimal
    previous_revenue: Decimal
    current_transactions: int
    previous_transactions: int
    current_average_order_value: Decimal
    previous_average_order_value: Decimal
    revenue_growth_percent: Decimal | None
    transaction_growth_percent: Decimal | None
    average_order_value_growth_percent: Decimal | None


class SalesContext(ApiSchema):
    today: SalesMetric
    last_7_days: SalesMetric
    previous_7_days: SalesMetric
    growth_7_days_percent: Decimal | None
    last_30_days: SalesMetric
    previous_30_days: SalesMetric
    growth_30_days_percent: Decimal | None
    daily_trend: list[DailySales]
    trends: list[PeriodSalesTrend]


class ProductPerformance(ApiSchema):
    product_id: UUID
    name: str
    sku: str
    category: str
    units_sold: int
    revenue: Decimal
    previous_units_sold: int = 0
    previous_revenue: Decimal = Decimal("0.00")
    revenue_contribution_percent: Decimal = Decimal("0.00")
    growth_percent: Decimal | None = None


class CategoryPerformance(ApiSchema):
    category: str
    revenue: Decimal
    units_sold: int
    previous_revenue: Decimal = Decimal("0.00")
    previous_units_sold: int = 0
    revenue_contribution_percent: Decimal = Decimal("0.00")
    growth_percent: Decimal | None = None


class ProductsContext(ApiSchema):
    total_products: int
    total_categories: int
    category_sales_30_days: list[CategoryPerformance]
    top_selling_30_days: list[ProductPerformance]
    slow_moving_30_days: list[ProductPerformance]
    fast_moving_7_days: list[ProductPerformance]
    bottom_selling_30_days: list[ProductPerformance]
    declining_products_30_days: list[ProductPerformance]
    growing_products_30_days: list[ProductPerformance]
    category_performance_30_days: list[CategoryPerformance]


class StockRisk(ApiSchema):
    product_id: UUID
    name: str
    sku: str
    category: str
    current_stock: int
    reorder_threshold: int
    units_sold_7_days: int
    estimated_days_of_stock: Decimal | None
    risk: Literal["low_stock", "stockout_risk"]


class InventoryProductIntelligence(ApiSchema):
    product_id: UUID
    name: str
    sku: str
    category: str
    current_stock: int
    reorder_threshold: int
    units_sold_30_days: int
    units_sold_7_days: int
    average_daily_units_sold: Decimal
    estimated_days_of_stock: Decimal | None


class StockMovementSummary(ApiSchema):
    movement_type: str
    movement_count: int
    net_units: int


class InventoryContext(ApiSchema):
    products_with_stock: int
    total_units_in_stock: int
    low_stock_count: int
    stockout_count: int
    low_stock_products: list[StockRisk]
    products_at_stockout_risk: list[StockRisk]
    fast_moving_low_stock_products: list[StockRisk]
    fast_moving_products: list[InventoryProductIntelligence]
    excess_or_slow_moving_products: list[InventoryProductIntelligence]
    movement_summary_30_days: list[StockMovementSummary]


class CustomerSegment(ApiSchema):
    customer_reference: str
    transactions: int
    total_spend: Decimal
    average_transaction_value: Decimal
    last_purchase_at: datetime


class CustomerContext(ApiSchema):
    customer_model_available: bool = False
    unique_customer_references_30_days: int
    repeat_customer_references_30_days: int
    single_purchase_references_30_days: int
    purchase_frequency_30_days: Decimal
    average_customer_transaction_value_30_days: Decimal
    active_customer_references_7_days: int
    previous_active_customer_references_7_days: int
    activity_growth_percent: Decimal | None
    repeat_customers: list[CustomerSegment] = Field(default_factory=list)
    note: str


class CampaignRecord(ApiSchema):
    id: UUID
    name: str
    channel: str
    status: str
    reach: str
    starts_at: datetime | None


class CampaignContext(ApiSchema):
    active: list[CampaignRecord]
    expired: list[CampaignRecord]
    scheduled: list[CampaignRecord]


OpportunityType = Literal[
    "SALES_DROP",
    "HIGH_GROWTH_PRODUCT",
    "LOW_STOCK_FAST_MOVER",
    "SLOW_MOVING_PRODUCT",
    "LOW_AVERAGE_ORDER_VALUE",
    "POPULAR_PRODUCT",
    "CATEGORY_DECLINE",
    "CATEGORY_GROWTH",
    "REPEAT_CUSTOMER_OPPORTUNITY",
]


OpportunitySeverity = Literal["info", "opportunity", "warning", "critical"]


class BusinessOpportunity(ApiSchema):
    type: OpportunityType
    severity: OpportunitySeverity
    title: str
    reason: str
    metrics: dict[str, Decimal | int | str]
    recommended_action: str


class MerchantBusinessContext(ApiSchema):
    generated_at: datetime
    timezone: str
    merchant: MerchantContextInfo
    sales: SalesContext
    products: ProductsContext
    inventory: InventoryContext
    customers: CustomerContext
    campaigns: CampaignContext
    opportunities: list[BusinessOpportunity] = Field(default_factory=list)


class AnalyzeRequest(ApiSchema):
    question: str | None = Field(default=None, max_length=600)


class ChatMessage(ApiSchema):
    role: Literal["merchant", "ai"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(ApiSchema):
    message: str = Field(min_length=1, max_length=800)
    conversation: list[ChatMessage] = Field(default_factory=list, max_length=12)


class EvidenceMetric(ApiSchema):
    key: str
    label: str
    value: Decimal | int | str
    unit: str | None = None


class CopilotInsight(ApiSchema):
    title: str
    explanation: str
    supporting_metrics: list[EvidenceMetric] = Field(default_factory=list)
    severity: Literal["info", "opportunity", "warning"] = "info"


class CopilotRecommendation(ApiSchema):
    title: str
    opportunity_type: OpportunityType | None = None
    what_is_happening: str = ""
    why_it_matters: str = ""
    reason: str
    explanation: str | None = None
    supporting_metrics: list[EvidenceMetric] = Field(default_factory=list)
    supporting_numbers: dict[str, Decimal | int | str] = Field(default_factory=dict)
    metrics: dict[str, Decimal | int | str] = Field(default_factory=dict)
    recommended_action: str = ""
    expected_impact: str
    confidence: float = Field(ge=0, le=1)
    action_type: Literal["RESTOCK_PRODUCT", "CREATE_PROMOTION", "CREATE_BUNDLE", "REVIEW_SALES"]
    action: str | None = None
    requires_approval: bool = True
    requires_confirmation: bool = True


class RecommendationResponse(ApiSchema):
    merchant_name: str
    recommendations: list[CopilotRecommendation]
    generated_at: datetime


class ChatResponse(ApiSchema):
    answer: str
    supporting_metrics: list[EvidenceMetric] = Field(default_factory=list)
    insufficient_data: bool = False
    generated_at: datetime


class CopilotAnalysis(ApiSchema):
    merchant_name: str
    provider: str
    summary: str
    insights: list[CopilotInsight]
    opportunities: list[BusinessOpportunity]
    recommended_actions: list[CopilotRecommendation]
    generated_at: datetime


class ProviderInsight(ApiSchema):
    title: str
    explanation: str
    metric_keys: list[str]
    severity: Literal["info", "opportunity", "warning"] = "info"


class ProviderRecommendation(ApiSchema):
    title: str
    reason: str
    metric_keys: list[str]
    expected_impact: str
    confidence: float = Field(ge=0, le=1)
    action_type: Literal["RESTOCK_PRODUCT", "CREATE_PROMOTION", "CREATE_BUNDLE", "REVIEW_SALES"]


class ProviderAnalysis(ApiSchema):
    summary: str
    insights: list[ProviderInsight]
    opportunities: list[ProviderInsight]
    recommended_actions: list[ProviderRecommendation]
