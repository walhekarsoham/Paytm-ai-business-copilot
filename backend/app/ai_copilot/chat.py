from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai_copilot.analytics import build_merchant_context
from app.ai_copilot.recommendations import build_recommendations
from app.ai_copilot.schemas import ChatResponse, EvidenceMetric, MerchantBusinessContext
from app.models import Merchant, Transaction, TransactionItem

MERCHANT_TIMEZONE = ZoneInfo("Asia/Kolkata")
ZERO = Decimal("0.00")


Intent = str


def _detect_intent(message: str) -> Intent:
    text = " ".join(message.lower().strip().split())
    greetings = {"hi", "hii", "hello", "hey", "heyy", "hola", "namaste"}
    if text in greetings or text.rstrip("!.") in greetings:
        return "GREETING"
    if any(term in text for term in ("create campaign", "start campaign", "make campaign", "run campaign", "campaign")):
        return "CAMPAIGNS"
    if any(term in text for term in ("restock", "low stock", "run out", "reorder")):
        return "INVENTORY_RESTOCK"
    if any(term in text for term in ("current inventory", "inventory", "stock summary", "stock level", "stock levels")):
        return "INVENTORY_SUMMARY"
    if any(term in text for term in ("top product", "top products", "best product", "best-selling", "best selling", "popular product")):
        return "PRODUCT_TOP"
    if any(term in text for term in ("slow moving", "slow-moving", "selling slowly", "bottom product", "dead stock")):
        return "PRODUCT_SLOW"
    if any(term in text for term in ("increase sales", "grow sales", "boost sales", "sell more", "what should i do")):
        return "GROWTH"
    if "today" in text and any(term in text for term in ("sell", "sales", "revenue", "business")):
        return "SALES_TODAY"
    if any(term in text for term in ("this month", "month's sales", "monthly sales", "month sales")):
        return "SALES_MONTH"
    if any(term in text for term in ("sales drop", "sales dropped", "sales fall", "sales fell", "why did sales", "decline")):
        return "SALES_DECLINE"
    if any(term in text for term in ("sales", "business doing", "how is my business", "this week", "week")):
        return "SALES_ANALYSIS"
    if any(term in text for term in ("customer", "repeat")):
        return "CUSTOMERS"
    if len(text.split()) <= 2:
        return "AMBIGUOUS"
    return "GENERAL_BUSINESS"


def _money(value: Decimal) -> str:
    return f"Rs {value:,.2f}"


def _metric(key: str, label: str, value: Decimal | int | str, unit: str | None = None) -> EvidenceMetric:
    return EvidenceMetric(key=key, label=label, value=value, unit=unit)


def _utc_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=MERCHANT_TIMEZONE).astimezone(timezone.utc)


def _growth(current: Decimal, previous: Decimal) -> Decimal | None:
    if previous <= 0:
        return None
    return ((current - previous) * Decimal("100") / previous).quantize(Decimal("0.01"))


def _sales_summary(database: Session, merchant_id, start: datetime, end: datetime) -> tuple[Decimal, int]:
    row = database.execute(
        select(func.coalesce(func.sum(Transaction.total), 0), func.count(Transaction.id)).where(
            Transaction.merchant_id == merchant_id,
            Transaction.created_at >= start,
            Transaction.created_at < end,
        )
    ).one()
    return row[0] or ZERO, int(row[1] or 0)


def _answer_greeting() -> ChatResponse:
    return ChatResponse(
        answer="Hi! I'm your AI business partner. How can I help with your business today?",
        supporting_metrics=[],
        generated_at=datetime.now(timezone.utc),
    )


def _answer_ambiguous() -> ChatResponse:
    return ChatResponse(
        answer="I can help with sales, products, inventory, customers, growth ideas, or campaigns. What would you like to look at?",
        supporting_metrics=[],
        insufficient_data=True,
        generated_at=datetime.now(timezone.utc),
    )


def _answer_today_sales(database: Session, merchant: Merchant) -> ChatResponse:
    today = datetime.now(timezone.utc).astimezone(MERCHANT_TIMEZONE).date()
    start = _utc_start(today)
    now = datetime.now(timezone.utc)
    sales, transactions = _sales_summary(database, merchant.id, start, now)
    return ChatResponse(
        answer=f"Today you have sold {_money(sales)} across {transactions} transactions so far.",
        supporting_metrics=[
            _metric("sales.today", "Today's sales", sales, "INR"),
            _metric("sales.today.transactions", "Today's transactions", transactions, "transactions"),
        ],
        generated_at=datetime.now(timezone.utc),
    )


def _answer_month_sales(database: Session, merchant: Merchant) -> ChatResponse:
    today = datetime.now(timezone.utc).astimezone(MERCHANT_TIMEZONE).date()
    month_start = _utc_start(today.replace(day=1))
    previous_month_day = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    previous_month_start = _utc_start(previous_month_day)
    now = datetime.now(timezone.utc)
    current_sales, current_transactions = _sales_summary(database, merchant.id, month_start, now)
    previous_sales, previous_transactions = _sales_summary(database, merchant.id, previous_month_start, month_start)
    growth = _growth(current_sales, previous_sales)
    metrics = [
        _metric("sales.month", "This month's sales", current_sales, "INR"),
        _metric("sales.month.transactions", "This month's transactions", current_transactions, "transactions"),
        _metric("sales.previous_month", "Previous month's sales", previous_sales, "INR"),
        _metric("sales.previous_month.transactions", "Previous month's transactions", previous_transactions, "transactions"),
    ]
    if growth is None:
        answer = f"This month you have sold {_money(current_sales)} across {current_transactions} transactions. I do not have enough previous-month sales to calculate a reliable percentage comparison."
        insufficient = previous_sales <= 0
    else:
        direction = "up" if growth >= 0 else "down"
        metrics.append(_metric("sales.month.growth", "This month change vs previous month", growth, "%"))
        answer = f"This month you have sold {_money(current_sales)} across {current_transactions} transactions, {direction} {abs(growth)}% from the previous month."
        insufficient = False
    return ChatResponse(answer=answer, supporting_metrics=metrics, insufficient_data=insufficient, generated_at=datetime.now(timezone.utc))


def _day_product_declines(database: Session, merchant_id, current_start: datetime, current_end: datetime, previous_start: datetime, previous_end: datetime) -> list[tuple[str, Decimal, Decimal, Decimal]]:
    current_sales = select(
        TransactionItem.product_name.label("name"),
        func.coalesce(func.sum(TransactionItem.line_total), 0).label("revenue"),
    ).join(Transaction, Transaction.id == TransactionItem.transaction_id).where(
        Transaction.merchant_id == merchant_id,
        Transaction.created_at >= current_start,
        Transaction.created_at < current_end,
    ).group_by(TransactionItem.product_name).subquery()
    previous_sales = select(
        TransactionItem.product_name.label("name"),
        func.coalesce(func.sum(TransactionItem.line_total), 0).label("revenue"),
    ).join(Transaction, Transaction.id == TransactionItem.transaction_id).where(
        Transaction.merchant_id == merchant_id,
        Transaction.created_at >= previous_start,
        Transaction.created_at < previous_end,
    ).group_by(TransactionItem.product_name).subquery()

    names = select(current_sales.c.name).union(select(previous_sales.c.name)).subquery()
    rows = database.execute(
        select(
            names.c.name,
            func.coalesce(current_sales.c.revenue, 0),
            func.coalesce(previous_sales.c.revenue, 0),
        )
        .outerjoin(current_sales, current_sales.c.name == names.c.name)
        .outerjoin(previous_sales, previous_sales.c.name == names.c.name)
    ).all()
    declines = []
    for row in rows:
        current = row[1] or ZERO
        previous = row[2] or ZERO
        delta = current - previous
        if delta < 0:
            declines.append((row[0], current, previous, delta))
    return sorted(declines, key=lambda item: item[3])[:3]


def _answer_week(context: MerchantBusinessContext) -> ChatResponse:
    sales = context.sales
    metrics = [
        _metric("sales.7d", "Sales in last 7 days", sales.last_7_days.sales, "INR"),
        _metric("sales.7d.transactions", "Transactions in last 7 days", sales.last_7_days.transactions, "transactions"),
        _metric("sales.previous_7d", "Sales in previous 7 days", sales.previous_7_days.sales, "INR"),
    ]
    if sales.growth_7_days_percent is None:
        answer = (
            f"This week, sales are {_money(sales.last_7_days.sales)} across {sales.last_7_days.transactions} transactions. "
            "I do not have enough previous-week sales to calculate a reliable percentage comparison."
        )
        insufficient = sales.previous_7_days.sales <= 0
    else:
        direction = "up" if sales.growth_7_days_percent >= 0 else "down"
        metrics.append(_metric("sales.7d.growth", "Sales change vs previous week", sales.growth_7_days_percent, "%"))
        answer = (
            f"This week, sales are {_money(sales.last_7_days.sales)} across {sales.last_7_days.transactions} transactions, "
            f"{direction} {abs(sales.growth_7_days_percent)}% from the previous week."
        )
        insufficient = False
    if context.products.top_selling_30_days:
        leader = context.products.top_selling_30_days[0]
        answer += f" Your leading recent product is {leader.name}, with {leader.units_sold} units sold in the last 30 days."
        metrics.extend([
            _metric(f"product.{leader.product_id}.units30", f"{leader.name} units sold in last 30 days", leader.units_sold, "units"),
            _metric(f"product.{leader.product_id}.revenue30", f"{leader.name} revenue in last 30 days", leader.revenue, "INR"),
        ])
    return ChatResponse(answer=answer, supporting_metrics=metrics, insufficient_data=insufficient, generated_at=datetime.now(timezone.utc))


def _answer_top_products(context: MerchantBusinessContext) -> ChatResponse:
    products = context.products.top_selling_30_days[:5]
    if not products:
        return ChatResponse(
            answer="I do not have enough product sales data to identify top products yet.",
            insufficient_data=True,
            generated_at=datetime.now(timezone.utc),
        )
    parts = [f"{index + 1}. {product.name}: {product.units_sold} units, {_money(product.revenue)}" for index, product in enumerate(products)]
    metrics = []
    for product in products:
        metrics.extend([
            _metric(f"product.{product.product_id}.units30", f"{product.name} units sold in last 30 days", product.units_sold, "units"),
            _metric(f"product.{product.product_id}.revenue30", f"{product.name} revenue in last 30 days", product.revenue, "INR"),
        ])
    return ChatResponse(
        answer="Your top products in the last 30 days are: " + " ".join(parts),
        supporting_metrics=metrics,
        generated_at=datetime.now(timezone.utc),
    )


def _answer_slow_products(context: MerchantBusinessContext) -> ChatResponse:
    products = context.inventory.excess_or_slow_moving_products[:5]
    if not products:
        return ChatResponse(
            answer="I do not see enough evidence of excess or slow-moving inventory right now.",
            insufficient_data=True,
            generated_at=datetime.now(timezone.utc),
        )
    parts = [f"{product.name}: {product.current_stock} in stock, {product.units_sold_30_days} sold in 30 days" for product in products]
    metrics = []
    for product in products:
        metrics.extend([
            _metric(f"product.{product.product_id}.stock", f"{product.name} current stock", product.current_stock, "units"),
            _metric(f"product.{product.product_id}.sold30", f"{product.name} units sold in last 30 days", product.units_sold_30_days, "units"),
        ])
    return ChatResponse(
        answer="These products are moving slowly: " + "; ".join(parts) + ".",
        supporting_metrics=metrics,
        generated_at=datetime.now(timezone.utc),
    )


def _answer_inventory_summary(context: MerchantBusinessContext) -> ChatResponse:
    inventory = context.inventory
    answer = (
        f"Current inventory has {inventory.total_units_in_stock} units across {inventory.products_with_stock} products. "
        f"{inventory.low_stock_count} products are at or below threshold, and {inventory.stockout_count} products are out of stock."
    )
    metrics = [
        _metric("inventory.total_units", "Total inventory units", inventory.total_units_in_stock, "units"),
        _metric("inventory.products", "Products in inventory", inventory.products_with_stock, "products"),
        _metric("inventory.low_stock", "Low-stock products", inventory.low_stock_count, "products"),
        _metric("inventory.stockout", "Out-of-stock products", inventory.stockout_count, "products"),
    ]
    return ChatResponse(answer=answer, supporting_metrics=metrics, generated_at=datetime.now(timezone.utc))


def _answer_sales_actions(context: MerchantBusinessContext) -> ChatResponse:
    recommendations = build_recommendations(context)
    if not recommendations:
        return ChatResponse(
            answer="I do not have enough detected opportunities to recommend a specific sales action yet. Add more sales and product movement data, then ask again.",
            insufficient_data=True,
            generated_at=datetime.now(timezone.utc),
        )
    top = recommendations[0]
    metrics = [_metric(f"recommendation.{key}", key.replace("_", " ").title(), value) for key, value in top.supporting_numbers.items()]
    answer = (
        f"Your top opportunity is {top.title}. {top.what_is_happening} "
        f"Recommendation: {top.recommended_action} Expected impact: {top.expected_impact}"
    )
    return ChatResponse(answer=answer, supporting_metrics=metrics, generated_at=datetime.now(timezone.utc))


def _answer_sales_decline(context: MerchantBusinessContext) -> ChatResponse:
    sales = context.sales
    metrics = [
        _metric("sales.7d", "Sales in last 7 days", sales.last_7_days.sales, "INR"),
        _metric("sales.previous_7d", "Sales in previous 7 days", sales.previous_7_days.sales, "INR"),
    ]
    if sales.growth_7_days_percent is None:
        return ChatResponse(
            answer="I cannot explain a sales drop reliably because there is not enough previous-week sales data to compare against.",
            supporting_metrics=metrics,
            insufficient_data=True,
            generated_at=datetime.now(timezone.utc),
        )
    metrics.append(_metric("sales.growth_7d", "Sales change vs previous 7 days", sales.growth_7_days_percent, "%"))
    if sales.growth_7_days_percent >= 0:
        return ChatResponse(
            answer=f"I do not see a weekly sales drop in the retrieved data. Sales are up {sales.growth_7_days_percent}% versus the previous week.",
            supporting_metrics=metrics,
            generated_at=datetime.now(timezone.utc),
        )
    detail = ""
    if context.products.declining_products_30_days:
        product = context.products.declining_products_30_days[0]
        detail = f" A product contributing to decline is {product.name}, with revenue down {abs(product.growth_percent or ZERO)}% versus the previous 30 days."
        metrics.extend([
            _metric(f"product.{product.product_id}.revenue30", f"{product.name} current 30-day revenue", product.revenue, "INR"),
            _metric(f"product.{product.product_id}.previous_revenue30", f"{product.name} previous 30-day revenue", product.previous_revenue, "INR"),
        ])
    return ChatResponse(
        answer=f"Sales are down {abs(sales.growth_7_days_percent)}% versus the previous week.{detail}",
        supporting_metrics=metrics,
        generated_at=datetime.now(timezone.utc),
    )


def _answer_customers(context: MerchantBusinessContext) -> ChatResponse:
    customers = context.customers
    metrics = [
        _metric("customers.unique_30d", "Unique customer references in last 30 days", customers.unique_customer_references_30_days, "references"),
        _metric("customers.repeat_30d", "Repeat customer references in last 30 days", customers.repeat_customer_references_30_days, "references"),
        _metric("customers.average_transaction_value_30d", "Average customer transaction value", customers.average_customer_transaction_value_30_days, "INR"),
    ]
    return ChatResponse(
        answer=(
            f"In the last 30 days, I can identify {customers.unique_customer_references_30_days} customer references. "
            f"{customers.repeat_customer_references_30_days} made repeat purchases, and the average customer transaction value is {_money(customers.average_customer_transaction_value_30_days)}."
        ),
        supporting_metrics=metrics,
        insufficient_data=customers.unique_customer_references_30_days == 0,
        generated_at=datetime.now(timezone.utc),
    )


def _answer_campaign_flow(context: MerchantBusinessContext) -> ChatResponse:
    recommendations = build_recommendations(context)
    promo = next((item for item in recommendations if item.action_type in {"CREATE_PROMOTION", "CREATE_BUNDLE"}), None)
    if promo is None:
        return ChatResponse(
            answer="I can help start a campaign, but I do not have a specific campaign opportunity from the current data. Do you want a sales promotion, slow-moving product offer, or repeat-customer campaign?",
            insufficient_data=True,
            generated_at=datetime.now(timezone.utc),
        )
    metrics = [_metric(f"campaign_recommendation.{key}", key.replace("_", " ").title(), value) for key, value in promo.supporting_numbers.items()]
    return ChatResponse(
        answer=f"I can help start a campaign flow. Best campaign idea: {promo.title}. {promo.recommended_action} This requires merchant approval before anything is created.",
        supporting_metrics=metrics,
        generated_at=datetime.now(timezone.utc),
    )


def _answer_restock(context: MerchantBusinessContext) -> ChatResponse:
    risks = context.inventory.fast_moving_low_stock_products[:3]
    if not risks:
        return ChatResponse(
            answer="I do not see enough evidence of fast-moving low-stock products right now. No restock recommendation is supported by the current sales and stock data.",
            insufficient_data=True,
            generated_at=datetime.now(timezone.utc),
        )
    parts = []
    metrics: list[EvidenceMetric] = []
    for risk in risks:
        days = f", about {risk.estimated_days_of_stock} days of stock left" if risk.estimated_days_of_stock is not None else ""
        parts.append(f"{risk.name}: {risk.current_stock} units on hand, {risk.units_sold_7_days} sold in 7 days{days}")
        metrics.extend([
            _metric(f"product.{risk.product_id}.stock", f"{risk.name} stock", risk.current_stock, "units"),
            _metric(f"product.{risk.product_id}.sold7", f"{risk.name} units sold in 7 days", risk.units_sold_7_days, "units"),
        ])
        if risk.estimated_days_of_stock is not None:
            metrics.append(_metric(f"product.{risk.product_id}.days_cover", f"{risk.name} estimated days of stock", risk.estimated_days_of_stock, "days"))
    return ChatResponse(
        answer="These products should be reviewed for restock: " + "; ".join(parts) + ".",
        supporting_metrics=metrics,
        generated_at=datetime.now(timezone.utc),
    )


def _answer_yesterday_drop(database: Session, merchant: Merchant) -> ChatResponse:
    today = datetime.now(timezone.utc).astimezone(MERCHANT_TIMEZONE).date()
    yesterday = today - timedelta(days=1)
    previous = today - timedelta(days=2)
    yesterday_start = _utc_start(yesterday)
    today_start = _utc_start(today)
    previous_start = _utc_start(previous)
    yesterday_sales, yesterday_transactions = _sales_summary(database, merchant.id, yesterday_start, today_start)
    previous_sales, previous_transactions = _sales_summary(database, merchant.id, previous_start, yesterday_start)
    metrics = [
        _metric("sales.yesterday", "Yesterday sales", yesterday_sales, "INR"),
        _metric("sales.yesterday.transactions", "Yesterday transactions", yesterday_transactions, "transactions"),
        _metric("sales.previous_day", "Previous comparable day sales", previous_sales, "INR"),
        _metric("sales.previous_day.transactions", "Previous comparable day transactions", previous_transactions, "transactions"),
    ]
    if previous_sales <= 0:
        return ChatResponse(
            answer=(
                f"Yesterday sales were {_money(yesterday_sales)} across {yesterday_transactions} transactions. "
                "I cannot calculate why sales fell because the previous comparable day has no sales to compare against."
            ),
            supporting_metrics=metrics,
            insufficient_data=True,
            generated_at=datetime.now(timezone.utc),
        )
    growth = _growth(yesterday_sales, previous_sales)
    if growth is None or growth >= 0:
        metrics.append(_metric("sales.yesterday.change", "Yesterday change vs previous comparable day", growth or ZERO, "%"))
        return ChatResponse(
            answer=(
                f"Yesterday sales were {_money(yesterday_sales)} across {yesterday_transactions} transactions, "
                f"not lower than the previous comparable day of {_money(previous_sales)}."
            ),
            supporting_metrics=metrics,
            generated_at=datetime.now(timezone.utc),
        )
    declines = _day_product_declines(database, merchant.id, yesterday_start, today_start, previous_start, yesterday_start)
    metrics.append(_metric("sales.yesterday.change", "Yesterday change vs previous comparable day", growth, "%"))
    if declines:
        name, current, prior, delta = declines[0]
        metrics.extend([
            _metric("sales.yesterday.largest_product_decline.product", "Largest product decline", name),
            _metric("sales.yesterday.largest_product_decline.current", f"{name} yesterday revenue", current, "INR"),
            _metric("sales.yesterday.largest_product_decline.previous", f"{name} previous day revenue", prior, "INR"),
        ])
        reason = f" The largest product-level decline came from {name}, down {_money(abs(delta))} versus the previous comparable day."
    else:
        reason = " I do not have enough product-level line-item data to isolate the largest decline."
    return ChatResponse(
        answer=(
            f"Yesterday sales were {_money(yesterday_sales)} across {yesterday_transactions} transactions, "
            f"down {abs(growth)}% from {_money(previous_sales)} on the previous comparable day.{reason}"
        ),
        supporting_metrics=metrics,
        generated_at=datetime.now(timezone.utc),
    )


def chat_with_copilot(database: Session, merchant: Merchant, message: str) -> ChatResponse:
    intent = _detect_intent(message)
    if intent == "GREETING":
        return _answer_greeting()
    if intent == "AMBIGUOUS":
        return _answer_ambiguous()
    if intent == "SALES_TODAY":
        return _answer_today_sales(database, merchant)
    if intent == "SALES_MONTH":
        return _answer_month_sales(database, merchant)
    if intent == "SALES_DECLINE" and "yesterday" in message.lower():
        return _answer_yesterday_drop(database, merchant)

    context = build_merchant_context(database, merchant)
    if intent == "INVENTORY_RESTOCK":
        return _answer_restock(context)
    if intent == "INVENTORY_SUMMARY":
        return _answer_inventory_summary(context)
    if intent == "PRODUCT_TOP":
        return _answer_top_products(context)
    if intent == "PRODUCT_SLOW":
        return _answer_slow_products(context)
    if intent == "GROWTH":
        return _answer_sales_actions(context)
    if intent == "CAMPAIGNS":
        return _answer_campaign_flow(context)
    if intent == "SALES_DECLINE":
        return _answer_sales_decline(context)
    if intent == "CUSTOMERS":
        return _answer_customers(context)
    if intent == "SALES_ANALYSIS":
        return _answer_week(context)
    if context.sales.last_30_days.transactions == 0:
        return ChatResponse(
            answer="I do not have enough sales data to answer that reliably yet. Record sales first, then I can compare trends and recommend actions.",
            insufficient_data=True,
            generated_at=datetime.now(timezone.utc),
        )
    return ChatResponse(
        answer="I can help with sales, products, inventory, customers, growth ideas, or campaigns. Which area should I analyze?",
        insufficient_data=True,
        generated_at=datetime.now(timezone.utc),
    )
