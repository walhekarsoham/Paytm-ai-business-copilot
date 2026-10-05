from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_merchant, get_db
from app.models import Merchant, Product, Transaction, TransactionItem
from app.schemas import AnalyticsPeriod, DashboardRead, Insight, InventoryAlert, SalesPoint, TopProductSummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _month_start(value: date, months_before: int = 0) -> date:
    month_index = value.year * 12 + value.month - 1 - months_before
    year, month_index = divmod(month_index, 12)
    return date(year, month_index + 1, 1)


def _normalize_bucket(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _bucket_expression(database: Session, period: AnalyticsPeriod):
    if database.bind is not None and database.bind.dialect.name == "sqlite":
        if period == "12m":
            return func.strftime("%Y-%m-01", Transaction.created_at)
        return func.date(Transaction.created_at)
    unit = "month" if period == "12m" else "day"
    return cast(func.date_trunc(unit, Transaction.created_at), Date)


def _grouped_sales(
    database: Session,
    merchant_id,
    start: datetime,
    end: datetime,
    period: AnalyticsPeriod,
) -> dict[date, Decimal]:
    bucket = _bucket_expression(database, period)
    rows = database.execute(
        select(bucket, func.sum(Transaction.total))
        .where(
            Transaction.merchant_id == merchant_id,
            Transaction.created_at >= start,
            Transaction.created_at < end,
        )
        .group_by(bucket)
        .order_by(bucket)
    ).all()
    return {_normalize_bucket(bucket_date): amount or Decimal("0.00") for bucket_date, amount in rows}


def _period_bounds(period: AnalyticsPeriod, now: datetime) -> tuple[datetime, datetime, datetime, datetime, list[date]]:
    today = now.date()
    if period == "12m":
        current_start_day = _month_start(today, 11)
        previous_start_day = _month_start(current_start_day, 12)
        bucket_dates = [_month_start(today, 11 - index) for index in range(12)]
    else:
        period_days = 7 if period == "7d" else 30
        current_start_day = today - timedelta(days=period_days - 1)
        previous_start_day = current_start_day - timedelta(days=period_days)
        bucket_dates = [current_start_day + timedelta(days=index) for index in range(period_days)]

    current_start = datetime.combine(current_start_day, time.min, tzinfo=timezone.utc)
    current_end = now
    previous_start = datetime.combine(previous_start_day, time.min, tzinfo=timezone.utc)
    previous_end = current_start
    return current_start, current_end, previous_start, previous_end, bucket_dates


def _previous_bucket(bucket_date: date, period: AnalyticsPeriod) -> date:
    if period == "12m":
        return _month_start(bucket_date, 12)
    return bucket_date - timedelta(days=7 if period == "7d" else 30)


def _bucket_label(bucket_date: date, period: AnalyticsPeriod) -> str:
    if period == "7d":
        return bucket_date.strftime("%a")
    if period == "30d":
        return f"{bucket_date.strftime('%b')} {bucket_date.day}"
    return bucket_date.strftime("%b %y")


@router.get("", response_model=DashboardRead)
def dashboard_metrics(
    period: AnalyticsPeriod = Query(default="7d"),
    database: Session = Depends(get_db),
    merchant: Merchant = Depends(get_current_merchant),
) -> DashboardRead:
    now = datetime.now(timezone.utc)
    current_start, current_end, previous_start, previous_end, bucket_dates = _period_bounds(period, now)
    merchant_id = merchant.id
    current_metrics = database.execute(
        select(
            func.coalesce(func.sum(Transaction.total), 0),
            func.count(Transaction.id),
            func.count(func.distinct(Transaction.customer_reference)),
        ).where(
            Transaction.merchant_id == merchant_id,
            Transaction.created_at >= current_start,
            Transaction.created_at < current_end,
        )
    ).one()
    previous_sales = database.scalar(
        select(func.coalesce(func.sum(Transaction.total), 0)).where(
            Transaction.merchant_id == merchant_id,
            Transaction.created_at >= previous_start,
            Transaction.created_at < previous_end,
        )
    ) or Decimal("0.00")
    total_sales = current_metrics[0] or Decimal("0.00")
    total_orders = current_metrics[1] or 0
    customers = current_metrics[2] or 0
    sales_change_percent = (
        ((total_sales - previous_sales) * Decimal("100") / previous_sales).quantize(Decimal("0.01"))
        if previous_sales > 0 else None
    )

    current_series = _grouped_sales(database, merchant_id, current_start, current_end, period)
    previous_series = _grouped_sales(database, merchant_id, previous_start, previous_end, period)
    sales_series = [
        SalesPoint(
            label=_bucket_label(bucket_date, period),
            current=current_series.get(bucket_date, Decimal("0.00")),
            previous=previous_series.get(_previous_bucket(bucket_date, period), Decimal("0.00")),
        )
        for bucket_date in bucket_dates
    ]

    product_rows = database.execute(
        select(
            TransactionItem.product_name,
            TransactionItem.sku,
            Product.category,
            func.sum(TransactionItem.quantity).label("sold"),
            func.sum(TransactionItem.line_total).label("revenue"),
        )
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .outerjoin(Product, Product.id == TransactionItem.product_id)
        .where(
            Transaction.merchant_id == merchant_id,
            Transaction.created_at >= current_start,
            Transaction.created_at < current_end,
        )
        .group_by(TransactionItem.product_name, TransactionItem.sku, Product.category)
        .order_by(func.sum(TransactionItem.line_total).desc(), func.sum(TransactionItem.quantity).desc())
        .limit(5)
    ).all()
    top_revenue = max((row.revenue for row in product_rows), default=Decimal("0.00"))
    tones = ("mint", "lavender", "peach", "blue")
    top_products = [
        TopProductSummary(
            name=row.product_name,
            category=f"{row.category or 'Previously sold'} · SKU {row.sku}",
            sold=int(row.sold),
            revenue=row.revenue,
            share=int(row.revenue * 100 / top_revenue) if top_revenue else 0,
            tone=tones[index % len(tones)],
            initials="".join(word[0] for word in row.product_name.split()[:2]).upper(),
        )
        for index, row in enumerate(product_rows)
    ]

    low_products = database.scalars(
        select(Product)
        .where(Product.merchant_id == merchant_id, Product.stock_quantity <= Product.low_stock_threshold)
        .order_by(Product.stock_quantity, Product.name)
        .limit(5)
    ).all()
    inventory_alerts = [
        InventoryAlert(
            name=product.name,
            sku=product.sku,
            stock=product.stock_quantity,
            status="Out of stock" if product.stock_quantity == 0 else "Low stock",
            tone="critical" if product.stock_quantity == 0 or product.stock_quantity <= max(1, product.low_stock_threshold // 2) else "warning",
        )
        for product in low_products
    ]
    insights = []
    if inventory_alerts:
        insights.append(Insight(
            title=f"{len(inventory_alerts)} products need a stock check",
            description="Review low-stock grocery items and record supplier deliveries before they run out.",
            tag="INVENTORY",
            tone="blue",
        ))
    else:
        insights.append(Insight(
            title="Stock levels are looking healthy",
            description="No products are currently at or below their low-stock threshold.",
            tag="INVENTORY",
            tone="mint",
        ))
    if top_products:
        insights.append(Insight(
            title=f"{top_products[0].name} leads recorded sales",
            description=f"It has generated ₹{top_products[0].revenue:,.2f} across recorded transactions.",
            tag="SALES TREND",
            tone="violet",
        ))
    else:
        insights.append(Insight(
            title="Your first sale is ready to record",
            description="Record a sale to start tracking product revenue and sales trends here.",
            tag="SALES TREND",
            tone="violet",
        ))

    return DashboardRead(
        period=period,
        total_sales=total_sales,
        total_orders=total_orders,
        customers=customers,
        average_order_value=(Decimal(total_sales) / total_orders).quantize(Decimal("0.01")) if total_orders else Decimal("0.00"),
        sales_change_percent=sales_change_percent,
        sales_series=sales_series,
        top_products=top_products,
        inventory_alerts=inventory_alerts,
        insights=insights,
    )