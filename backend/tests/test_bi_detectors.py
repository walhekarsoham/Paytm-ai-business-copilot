from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.ai_copilot.detectors import detect_opportunities
from app.ai_copilot.recommendations import build_recommendations
from app.ai_copilot.schemas import (
    CampaignContext,
    CategoryPerformance,
    CustomerContext,
    InventoryContext,
    InventoryProductIntelligence,
    MerchantBusinessContext,
    MerchantContextInfo,
    PeriodSalesTrend,
    ProductPerformance,
    ProductsContext,
    SalesContext,
    SalesMetric,
    StockRisk,
)


def _sales(value: str, transactions: int) -> SalesMetric:
    amount = Decimal(value)
    return SalesMetric(
        sales=amount,
        transactions=transactions,
        unique_customer_references=transactions,
        average_order_value=(amount / Decimal(transactions)).quantize(Decimal("0.01")) if transactions else Decimal("0.00"),
    )


def _period(period: str) -> PeriodSalesTrend:
    return PeriodSalesTrend(
        period=period,
        current_revenue=Decimal("0.00"),
        previous_revenue=Decimal("0.00"),
        current_transactions=0,
        previous_transactions=0,
        current_average_order_value=Decimal("0.00"),
        previous_average_order_value=Decimal("0.00"),
        revenue_growth_percent=None,
        transaction_growth_percent=None,
        average_order_value_growth_percent=None,
    )


def _product(
    *,
    revenue: str = "0.00",
    previous_revenue: str = "0.00",
    units: int = 0,
    growth: str | None = None,
) -> ProductPerformance:
    return ProductPerformance(
        product_id=uuid4(),
        name="Growth Tea",
        sku="TEA-001",
        category="Beverages",
        units_sold=units,
        revenue=Decimal(revenue),
        previous_units_sold=1,
        previous_revenue=Decimal(previous_revenue),
        revenue_contribution_percent=Decimal("10.00"),
        growth_percent=Decimal(growth) if growth is not None else None,
    )


def _category(growth: str, *, name: str = "Snacks") -> CategoryPerformance:
    return CategoryPerformance(
        category=name,
        revenue=Decimal("500.00"),
        units_sold=20,
        previous_revenue=Decimal("300.00"),
        previous_units_sold=12,
        revenue_contribution_percent=Decimal("40.00"),
        growth_percent=Decimal(growth),
    )


def _inventory_item(*, stock: int = 40, units_30: int = 1) -> InventoryProductIntelligence:
    return InventoryProductIntelligence(
        product_id=uuid4(),
        name="Slow Rice",
        sku="RICE-001",
        category="Staples",
        current_stock=stock,
        reorder_threshold=5,
        units_sold_30_days=units_30,
        units_sold_7_days=0,
        average_daily_units_sold=Decimal("0.03"),
        estimated_days_of_stock=Decimal("1200.0"),
    )


def _stock_risk() -> StockRisk:
    return StockRisk(
        product_id=uuid4(),
        name="Fast Milk",
        sku="MILK-001",
        category="Dairy",
        current_stock=2,
        reorder_threshold=5,
        units_sold_7_days=12,
        estimated_days_of_stock=Decimal("1.2"),
        risk="low_stock",
    )


def _context(
    *,
    growth_7: str | None = None,
    last_30: SalesMetric | None = None,
    growing_products: list[ProductPerformance] | None = None,
    stock_risks: list[StockRisk] | None = None,
    slow_inventory: list[InventoryProductIntelligence] | None = None,
    categories: list[CategoryPerformance] | None = None,
    repeat_customers: int = 0,
    top_products: list[ProductPerformance] | None = None,
) -> MerchantBusinessContext:
    now = datetime.now(timezone.utc)
    current_7 = _sales("700.00", 7)
    previous_7 = _sales("1000.00", 10)
    current_30 = last_30 or _sales("3000.00", 20)
    return MerchantBusinessContext(
        generated_at=now,
        timezone="Asia/Kolkata",
        merchant=MerchantContextInfo(
            id=uuid4(),
            business_name="Detector Mart",
            merchant_type="Grocery merchant",
            merchant_type_source="test",
        ),
        sales=SalesContext(
            today=_sales("100.00", 1),
            last_7_days=current_7,
            previous_7_days=previous_7,
            growth_7_days_percent=Decimal(growth_7) if growth_7 is not None else None,
            last_30_days=current_30,
            previous_30_days=_sales("2000.00", 12),
            growth_30_days_percent=Decimal("50.00"),
            daily_trend=[],
            trends=[_period("daily"), _period("weekly"), _period("monthly")],
        ),
        products=ProductsContext(
            total_products=4,
            total_categories=2,
            category_sales_30_days=categories or [],
            top_selling_30_days=top_products or [],
            slow_moving_30_days=[],
            fast_moving_7_days=[],
            bottom_selling_30_days=[],
            declining_products_30_days=[],
            growing_products_30_days=growing_products or [],
            category_performance_30_days=categories or [],
        ),
        inventory=InventoryContext(
            products_with_stock=4,
            total_units_in_stock=100,
            low_stock_count=len(stock_risks or []),
            stockout_count=0,
            low_stock_products=stock_risks or [],
            products_at_stockout_risk=stock_risks or [],
            fast_moving_low_stock_products=stock_risks or [],
            fast_moving_products=[],
            excess_or_slow_moving_products=slow_inventory or [],
            movement_summary_30_days=[],
        ),
        customers=CustomerContext(
            unique_customer_references_30_days=max(repeat_customers, 1),
            repeat_customer_references_30_days=repeat_customers,
            single_purchase_references_30_days=1,
            purchase_frequency_30_days=Decimal("2.00"),
            average_customer_transaction_value_30_days=Decimal("175.00"),
            active_customer_references_7_days=3,
            previous_active_customer_references_7_days=2,
            activity_growth_percent=Decimal("50.00"),
            repeat_customers=[],
            note="test",
        ),
        campaigns=CampaignContext(active=[], expired=[], scheduled=[]),
    )


def _assert_shape(opportunity_type: str, context: MerchantBusinessContext) -> None:
    opportunity = next(item for item in detect_opportunities(context) if item.type == opportunity_type)
    payload = opportunity.model_dump()
    assert set(payload) == {"type", "severity", "title", "reason", "metrics", "recommended_action"}
    assert payload["type"] == opportunity_type
    assert payload["severity"]
    assert payload["title"]
    assert payload["reason"]
    assert payload["metrics"]
    assert payload["recommended_action"]


def test_sales_drop_detector() -> None:
    _assert_shape("SALES_DROP", _context(growth_7="-30.00"))


def test_high_growth_product_detector() -> None:
    _assert_shape("HIGH_GROWTH_PRODUCT", _context(growing_products=[_product(revenue="300.00", previous_revenue="100.00", units=6, growth="200.00")]))


def test_popular_product_detector() -> None:
    popular = _product(revenue="1500.00", units=12)
    popular.revenue_contribution_percent = Decimal("50.00")
    _assert_shape("POPULAR_PRODUCT", _context(top_products=[popular]))


def test_low_stock_fast_mover_detector() -> None:
    _assert_shape("LOW_STOCK_FAST_MOVER", _context(stock_risks=[_stock_risk()]))


def test_slow_moving_product_detector() -> None:
    _assert_shape("SLOW_MOVING_PRODUCT", _context(slow_inventory=[_inventory_item()]))


def test_low_average_order_value_detector() -> None:
    _assert_shape("LOW_AVERAGE_ORDER_VALUE", _context(last_30=_sales("600.00", 6)))


def test_category_decline_detector() -> None:
    _assert_shape("CATEGORY_DECLINE", _context(categories=[_category("-25.00")]))


def test_category_growth_detector() -> None:
    _assert_shape("CATEGORY_GROWTH", _context(categories=[_category("66.67")]))


def test_repeat_customer_opportunity_detector() -> None:
    _assert_shape("REPEAT_CUSTOMER_OPPORTUNITY", _context(repeat_customers=3))


def test_recommendations_convert_opportunities_into_approval_required_actions() -> None:
    context = _context(stock_risks=[_stock_risk()])
    context.opportunities = detect_opportunities(context)

    recommendations = build_recommendations(context)

    assert recommendations
    recommendation = recommendations[0]
    assert recommendation.opportunity_type == "LOW_STOCK_FAST_MOVER"
    assert recommendation.what_is_happening
    assert recommendation.why_it_matters
    assert recommendation.supporting_numbers
    assert recommendation.recommended_action
    assert recommendation.expected_impact
    assert 0 < recommendation.confidence <= 1
    assert recommendation.requires_approval is True
