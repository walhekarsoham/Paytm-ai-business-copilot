from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.ai_copilot.detectors import detect_opportunities
from app.ai_copilot.schemas import (
    CampaignContext,
    CampaignRecord,
    CategoryPerformance,
    CustomerSegment,
    CustomerContext,
    DailySales,
    InventoryProductIntelligence,
    InventoryContext,
    MerchantBusinessContext,
    MerchantContextInfo,
    PeriodSalesTrend,
    ProductPerformance,
    ProductsContext,
    SalesContext,
    SalesMetric,
    StockMovementSummary,
    StockRisk,
)
from app.models import Campaign, InventoryMovement, Merchant, Product, Transaction, TransactionItem

MERCHANT_TIMEZONE = ZoneInfo("Asia/Kolkata")
ZERO = Decimal("0.00")


def _utc_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=MERCHANT_TIMEZONE).astimezone(timezone.utc)


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _day_bucket(database: Session):
    if database.bind is not None and database.bind.dialect.name == "sqlite":
        return func.date(Transaction.created_at)
    return cast(func.date_trunc("day", func.timezone("Asia/Kolkata", Transaction.created_at)), Date)


def _sales_metric(database: Session, merchant_id, start: datetime, end: datetime) -> SalesMetric:
    row = database.execute(
        select(
            func.coalesce(func.sum(Transaction.total), 0),
            func.count(Transaction.id),
            func.count(func.distinct(Transaction.customer_reference)),
        ).where(
            Transaction.merchant_id == merchant_id,
            Transaction.created_at >= start,
            Transaction.created_at < end,
        )
    ).one()
    sales = row[0] or ZERO
    orders = int(row[1] or 0)
    return SalesMetric(
        sales=sales,
        transactions=orders,
        unique_customer_references=int(row[2] or 0),
        average_order_value=(Decimal(sales) / orders).quantize(Decimal("0.01")) if orders else ZERO,
    )


def _growth(current: Decimal | int, previous: Decimal | int) -> Decimal | None:
    current_decimal = Decimal(current)
    previous_decimal = Decimal(previous)
    if previous_decimal <= 0:
        return None
    return ((current_decimal - previous_decimal) * Decimal("100") / previous_decimal).quantize(Decimal("0.01"))


def _period_trend(period: str, current: SalesMetric, previous: SalesMetric) -> PeriodSalesTrend:
    return PeriodSalesTrend(
        period=period,
        current_revenue=current.sales,
        previous_revenue=previous.sales,
        current_transactions=current.transactions,
        previous_transactions=previous.transactions,
        current_average_order_value=current.average_order_value,
        previous_average_order_value=previous.average_order_value,
        revenue_growth_percent=_growth(current.sales, previous.sales),
        transaction_growth_percent=_growth(current.transactions, previous.transactions),
        average_order_value_growth_percent=_growth(current.average_order_value, previous.average_order_value),
    )


def _product_performance(row) -> ProductPerformance:
    return ProductPerformance(
        product_id=row.id,
        name=row.name,
        sku=row.sku,
        category=row.category,
        units_sold=int(row.units_sold or 0),
        revenue=row.revenue or ZERO,
        previous_units_sold=int(getattr(row, "previous_units_sold", 0) or 0),
        previous_revenue=getattr(row, "previous_revenue", ZERO) or ZERO,
        revenue_contribution_percent=getattr(row, "revenue_contribution_percent", ZERO) or ZERO,
        growth_percent=getattr(row, "growth_percent", None),
    )


def build_merchant_context(database: Session, merchant: Merchant) -> MerchantBusinessContext:
    now = datetime.now(timezone.utc)
    today = now.astimezone(MERCHANT_TIMEZONE).date()
    today_start = _utc_start(today)
    yesterday_start = _utc_start(today - timedelta(days=1))
    last_7_start = _utc_start(today - timedelta(days=6))
    previous_7_start = _utc_start(today - timedelta(days=13))
    last_30_start = _utc_start(today - timedelta(days=29))
    previous_30_start = _utc_start(today - timedelta(days=59))
    month_start = _utc_start(today.replace(day=1))
    previous_month_day = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    previous_month_start = _utc_start(previous_month_day)

    today_sales = _sales_metric(database, merchant.id, today_start, now)
    yesterday_sales = _sales_metric(database, merchant.id, yesterday_start, today_start)
    last_7_sales = _sales_metric(database, merchant.id, last_7_start, now)
    previous_7_sales = _sales_metric(database, merchant.id, previous_7_start, last_7_start)
    last_30_sales = _sales_metric(database, merchant.id, last_30_start, now)
    previous_30_sales = _sales_metric(database, merchant.id, previous_30_start, last_30_start)
    month_sales = _sales_metric(database, merchant.id, month_start, now)
    previous_month_sales = _sales_metric(database, merchant.id, previous_month_start, month_start)
    growth_7 = _growth(last_7_sales.sales, previous_7_sales.sales)
    growth_30 = _growth(last_30_sales.sales, previous_30_sales.sales)

    day_bucket = _day_bucket(database)
    daily_rows = database.execute(
        select(day_bucket, func.coalesce(func.sum(Transaction.total), 0), func.count(Transaction.id))
        .where(
            Transaction.merchant_id == merchant.id,
            Transaction.created_at >= last_7_start,
            Transaction.created_at < now,
        )
        .group_by(day_bucket)
        .order_by(day_bucket)
    ).all()
    daily_map = {_as_date(row[0]): (row[1] or ZERO, int(row[2] or 0)) for row in daily_rows}
    daily_trend = [
        DailySales(
            day=datetime.combine(today - timedelta(days=offset), time.min, tzinfo=MERCHANT_TIMEZONE),
            sales=daily_map.get(today - timedelta(days=offset), (ZERO, 0))[0],
            transactions=daily_map.get(today - timedelta(days=offset), (ZERO, 0))[1],
        )
        for offset in range(6, -1, -1)
    ]

    products = list(database.scalars(
        select(Product).where(Product.merchant_id == merchant.id).order_by(Product.name)
    ).all())
    product_sales_30 = select(
        TransactionItem.product_id.label("product_id"),
        func.sum(TransactionItem.quantity).label("units_sold"),
        func.sum(TransactionItem.line_total).label("revenue"),
    ).join(Transaction, Transaction.id == TransactionItem.transaction_id).where(
        Transaction.merchant_id == merchant.id,
        Transaction.created_at >= last_30_start,
        Transaction.created_at < now,
        TransactionItem.product_id.is_not(None),
    ).group_by(TransactionItem.product_id).subquery()
    product_sales_previous_30 = select(
        TransactionItem.product_id.label("product_id"),
        func.sum(TransactionItem.quantity).label("units_sold"),
        func.sum(TransactionItem.line_total).label("revenue"),
    ).join(Transaction, Transaction.id == TransactionItem.transaction_id).where(
        Transaction.merchant_id == merchant.id,
        Transaction.created_at >= previous_30_start,
        Transaction.created_at < last_30_start,
        TransactionItem.product_id.is_not(None),
    ).group_by(TransactionItem.product_id).subquery()
    product_sales_7 = select(
        TransactionItem.product_id.label("product_id"),
        func.sum(TransactionItem.quantity).label("units_sold"),
        func.sum(TransactionItem.line_total).label("revenue"),
    ).join(Transaction, Transaction.id == TransactionItem.transaction_id).where(
        Transaction.merchant_id == merchant.id,
        Transaction.created_at >= last_7_start,
        Transaction.created_at < now,
        TransactionItem.product_id.is_not(None),
    ).group_by(TransactionItem.product_id).subquery()

    product_rows_30 = database.execute(
        select(
            Product.id,
            Product.name,
            Product.sku,
            Product.category,
            func.coalesce(product_sales_30.c.units_sold, 0).label("units_sold"),
            func.coalesce(product_sales_30.c.revenue, 0).label("revenue"),
            func.coalesce(product_sales_previous_30.c.units_sold, 0).label("previous_units_sold"),
            func.coalesce(product_sales_previous_30.c.revenue, 0).label("previous_revenue"),
        )
        .outerjoin(product_sales_30, product_sales_30.c.product_id == Product.id)
        .outerjoin(product_sales_previous_30, product_sales_previous_30.c.product_id == Product.id)
        .where(Product.merchant_id == merchant.id)
    ).all()
    enriched_product_rows = []
    for row in product_rows_30:
        revenue = row.revenue or ZERO
        previous_revenue = row.previous_revenue or ZERO
        enriched_product_rows.append({
            **dict(row._mapping),
            "revenue_contribution_percent": (
                (Decimal(revenue) * Decimal("100") / last_30_sales.sales).quantize(Decimal("0.01"))
                if last_30_sales.sales > 0 else ZERO
            ),
            "growth_percent": _growth(revenue, previous_revenue),
        })

    class RowObject:
        def __init__(self, values):
            self.__dict__.update(values)

    product_rows = [RowObject(values) for values in enriched_product_rows]
    by_revenue = sorted(product_rows, key=lambda row: (row.revenue, row.units_sold), reverse=True)
    by_slow_motion = sorted(product_rows, key=lambda row: (row.units_sold, row.revenue, row.name))
    by_growth = sorted(
        [row for row in product_rows if row.growth_percent is not None],
        key=lambda row: (row.growth_percent, row.revenue),
        reverse=True,
    )
    by_decline = sorted(
        [row for row in product_rows if row.growth_percent is not None],
        key=lambda row: (row.growth_percent, row.revenue),
    )
    top_selling = [_product_performance(row) for row in by_revenue[:5] if row.units_sold]
    slow_moving = [_product_performance(row) for row in by_slow_motion[:5]]
    bottom_selling = [_product_performance(row) for row in by_slow_motion[:5]]
    growing_products = [_product_performance(row) for row in by_growth[:5] if row.growth_percent and row.growth_percent > 0]
    declining_products = [_product_performance(row) for row in by_decline[:5] if row.growth_percent and row.growth_percent < 0]

    category_current_rows = database.execute(
        select(
            Product.category,
            func.sum(TransactionItem.line_total).label("revenue"),
            func.sum(TransactionItem.quantity).label("units_sold"),
        )
        .join(TransactionItem, TransactionItem.product_id == Product.id)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .where(
            Product.merchant_id == merchant.id,
            Transaction.merchant_id == merchant.id,
            Transaction.created_at >= last_30_start,
            Transaction.created_at < now,
        )
        .group_by(Product.category)
        .order_by(func.sum(TransactionItem.line_total).desc())
    ).all()
    category_previous_rows = database.execute(
        select(
            Product.category,
            func.sum(TransactionItem.line_total).label("revenue"),
            func.sum(TransactionItem.quantity).label("units_sold"),
        )
        .join(TransactionItem, TransactionItem.product_id == Product.id)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .where(
            Product.merchant_id == merchant.id,
            Transaction.merchant_id == merchant.id,
            Transaction.created_at >= previous_30_start,
            Transaction.created_at < last_30_start,
        )
        .group_by(Product.category)
    ).all()
    previous_category = {
        row.category: (row.revenue or ZERO, int(row.units_sold or 0))
        for row in category_previous_rows
    }
    category_sales = [
        CategoryPerformance(
            category=row.category,
            revenue=row.revenue or ZERO,
            units_sold=int(row.units_sold or 0),
            previous_revenue=previous_category.get(row.category, (ZERO, 0))[0],
            previous_units_sold=previous_category.get(row.category, (ZERO, 0))[1],
            revenue_contribution_percent=(
                (Decimal(row.revenue or ZERO) * Decimal("100") / last_30_sales.sales).quantize(Decimal("0.01"))
                if last_30_sales.sales > 0 else ZERO
            ),
            growth_percent=_growth(row.revenue or ZERO, previous_category.get(row.category, (ZERO, 0))[0]),
        )
        for row in category_current_rows
    ]

    fast_rows = database.execute(
        select(
            Product.id,
            Product.name,
            Product.sku,
            Product.category,
            func.coalesce(product_sales_7.c.units_sold, 0).label("units_sold"),
            func.coalesce(product_sales_7.c.revenue, 0).label("revenue"),
        )
        .outerjoin(product_sales_7, product_sales_7.c.product_id == Product.id)
        .where(Product.merchant_id == merchant.id)
        .order_by(func.coalesce(product_sales_7.c.units_sold, 0).desc(), func.coalesce(product_sales_7.c.revenue, 0).desc())
        .limit(10)
    ).all()
    fast_products = [_product_performance(row) for row in fast_rows if row.units_sold]
    fast_units = {row.id: int(row.units_sold or 0) for row in fast_rows}

    risks: list[StockRisk] = []
    inventory_intelligence: list[InventoryProductIntelligence] = []
    units_30_by_id = {row.id: int(row.units_sold or 0) for row in product_rows}
    for product in products:
        sold_7 = fast_units.get(product.id, 0)
        sold_30 = units_30_by_id.get(product.id, 0)
        average_daily = Decimal(sold_7) / Decimal(7)
        average_daily_30 = Decimal(sold_30) / Decimal(30)
        days_cover = (Decimal(product.stock_quantity) / average_daily).quantize(Decimal("0.1")) if average_daily > 0 else None
        days_cover_30 = (Decimal(product.stock_quantity) / average_daily_30).quantize(Decimal("0.1")) if average_daily_30 > 0 else None
        inventory_intelligence.append(InventoryProductIntelligence(
            product_id=product.id,
            name=product.name,
            sku=product.sku,
            category=product.category,
            current_stock=product.stock_quantity,
            reorder_threshold=product.low_stock_threshold,
            units_sold_30_days=sold_30,
            units_sold_7_days=sold_7,
            average_daily_units_sold=average_daily_30.quantize(Decimal("0.01")),
            estimated_days_of_stock=days_cover_30,
        ))
        low_stock = product.stock_quantity <= product.low_stock_threshold
        stockout_risk = days_cover is not None and days_cover <= 7
        if low_stock or stockout_risk:
            risks.append(StockRisk(
                product_id=product.id,
                name=product.name,
                sku=product.sku,
                category=product.category,
                current_stock=product.stock_quantity,
                reorder_threshold=product.low_stock_threshold,
                units_sold_7_days=sold_7,
                estimated_days_of_stock=days_cover,
                risk="low_stock" if low_stock else "stockout_risk",
            ))
    risks.sort(key=lambda item: (item.risk != "low_stock", item.estimated_days_of_stock if item.estimated_days_of_stock is not None else Decimal("999999"), item.current_stock))
    fast_moving_low_stock = [
        risk for risk in risks if risk.units_sold_7_days > 0
    ][:5]
    low_stock_products = [risk for risk in risks if risk.current_stock <= risk.reorder_threshold][:10]
    products_at_risk = risks[:10]
    fast_moving_inventory = sorted(
        [item for item in inventory_intelligence if item.units_sold_30_days > 0],
        key=lambda item: (item.units_sold_30_days, item.units_sold_7_days),
        reverse=True,
    )[:10]
    excess_or_slow_moving = sorted(
        [
            item for item in inventory_intelligence
            if item.current_stock > item.reorder_threshold * 2 and item.units_sold_30_days <= max(2, item.current_stock // 10)
        ],
        key=lambda item: (-item.current_stock, item.units_sold_30_days, item.name),
    )[:10]

    movement_rows = database.execute(
        select(
            InventoryMovement.movement_type,
            func.count(InventoryMovement.id),
            func.coalesce(func.sum(InventoryMovement.quantity), 0),
        ).where(
            InventoryMovement.merchant_id == merchant.id,
            InventoryMovement.created_at >= last_30_start,
            InventoryMovement.created_at < now,
        ).group_by(InventoryMovement.movement_type).order_by(InventoryMovement.movement_type)
    ).all()
    movement_summary = [StockMovementSummary(movement_type=row[0], movement_count=int(row[1]), net_units=int(row[2])) for row in movement_rows]

    customer_rows = database.execute(
        select(
            Transaction.customer_reference,
            func.count(Transaction.id).label("order_count"),
            func.coalesce(func.sum(Transaction.total), 0).label("total_spend"),
            func.max(Transaction.created_at).label("last_purchase_at"),
        )
        .where(
            Transaction.merchant_id == merchant.id,
            Transaction.created_at >= last_30_start,
            Transaction.created_at < now,
            Transaction.customer_reference.is_not(None),
        )
        .group_by(Transaction.customer_reference)
    ).all()
    customer_counts = [int(row.order_count) for row in customer_rows]
    repeat_customers = [
        CustomerSegment(
            customer_reference=row.customer_reference,
            transactions=int(row.order_count),
            total_spend=row.total_spend or ZERO,
            average_transaction_value=(Decimal(row.total_spend or ZERO) / int(row.order_count)).quantize(Decimal("0.01")),
            last_purchase_at=row.last_purchase_at,
        )
        for row in customer_rows
        if int(row.order_count) > 1
    ]
    repeat_customers.sort(key=lambda item: (item.transactions, item.total_spend), reverse=True)
    active_7 = database.scalar(
        select(func.count(func.distinct(Transaction.customer_reference))).where(
            Transaction.merchant_id == merchant.id,
            Transaction.created_at >= last_7_start,
            Transaction.created_at < now,
            Transaction.customer_reference.is_not(None),
        )
    ) or 0
    previous_active_7 = database.scalar(
        select(func.count(func.distinct(Transaction.customer_reference))).where(
            Transaction.merchant_id == merchant.id,
            Transaction.created_at >= previous_7_start,
            Transaction.created_at < last_7_start,
            Transaction.customer_reference.is_not(None),
        )
    ) or 0
    customer_context = CustomerContext(
        unique_customer_references_30_days=len(customer_counts),
        repeat_customer_references_30_days=sum(count > 1 for count in customer_counts),
        single_purchase_references_30_days=sum(count == 1 for count in customer_counts),
        purchase_frequency_30_days=(Decimal(sum(customer_counts)) / Decimal(len(customer_counts))).quantize(Decimal("0.01")) if customer_counts else ZERO,
        average_customer_transaction_value_30_days=(
            (last_30_sales.sales / Decimal(sum(customer_counts))).quantize(Decimal("0.01"))
            if customer_counts and sum(customer_counts) else ZERO
        ),
        active_customer_references_7_days=int(active_7),
        previous_active_customer_references_7_days=int(previous_active_7),
        activity_growth_percent=_growth(int(active_7), int(previous_active_7)),
        repeat_customers=repeat_customers[:10],
        note="The current schema stores transaction customer references only; no customer profile/identity table is available.",
    )

    campaign_rows = list(database.scalars(
        select(Campaign).where(Campaign.merchant_id == merchant.id).order_by(Campaign.starts_at.desc().nullslast(), Campaign.created_at.desc())
    ).all())
    campaign_records = [CampaignRecord.model_validate(campaign) for campaign in campaign_rows]
    campaign_context = CampaignContext(
        active=[campaign for campaign in campaign_records if campaign.status.lower() == "active"],
        expired=[campaign for campaign in campaign_records if campaign.status.lower() == "expired"],
        scheduled=[campaign for campaign in campaign_records if campaign.status.lower() == "scheduled"],
    )

    context = MerchantBusinessContext(
        generated_at=now,
        timezone="Asia/Kolkata",
        merchant=MerchantContextInfo(
            id=merchant.id,
            business_name=merchant.business_name,
            merchant_type="Grocery merchant",
            merchant_type_source="Application specialization; the database schema has no merchant-type column.",
        ),
        sales=SalesContext(
            today=today_sales,
            last_7_days=last_7_sales,
            previous_7_days=previous_7_sales,
            growth_7_days_percent=growth_7,
            last_30_days=last_30_sales,
            previous_30_days=previous_30_sales,
            growth_30_days_percent=growth_30,
            daily_trend=daily_trend,
            trends=[
                _period_trend("daily", today_sales, yesterday_sales),
                _period_trend("weekly", last_7_sales, previous_7_sales),
                _period_trend("monthly", month_sales, previous_month_sales),
            ],
        ),
        products=ProductsContext(
            total_products=len(products),
            total_categories=len({product.category for product in products}),
            category_sales_30_days=category_sales,
            top_selling_30_days=top_selling,
            slow_moving_30_days=slow_moving,
            fast_moving_7_days=fast_products,
            bottom_selling_30_days=bottom_selling,
            declining_products_30_days=declining_products,
            growing_products_30_days=growing_products,
            category_performance_30_days=category_sales,
        ),
        inventory=InventoryContext(
            products_with_stock=len(products),
            total_units_in_stock=sum(product.stock_quantity for product in products),
            low_stock_count=sum(product.stock_quantity <= product.low_stock_threshold for product in products),
            stockout_count=sum(product.stock_quantity == 0 for product in products),
            low_stock_products=low_stock_products,
            products_at_stockout_risk=products_at_risk,
            fast_moving_low_stock_products=fast_moving_low_stock,
            fast_moving_products=fast_moving_inventory,
            excess_or_slow_moving_products=excess_or_slow_moving,
            movement_summary_30_days=movement_summary,
        ),
        customers=customer_context,
        campaigns=campaign_context,
    )
    context.opportunities = detect_opportunities(context)
    return context
