import re
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.ai_copilot.analytics import build_merchant_context
from app.ai_copilot.providers import AIProviderError, configured_provider
from app.ai_copilot.recommendations import build_recommendations
from app.ai_copilot.schemas import (
    BusinessOpportunity,
    CopilotAnalysis,
    CopilotInsight,
    CopilotRecommendation,
    EvidenceMetric,
    MerchantBusinessContext,
    ProviderAnalysis,
    RecommendationResponse,
)
from app.models import Merchant


def _format_money(value: Decimal) -> str:
    return f"₹{value:,.2f}"


def _evidence(context: MerchantBusinessContext) -> dict[str, EvidenceMetric]:
    metrics: dict[str, EvidenceMetric] = {}

    def add(key: str, label: str, value: Decimal | int | str, unit: str | None = None) -> None:
        metrics[key] = EvidenceMetric(key=key, label=label, value=value, unit=unit)

    sales = context.sales
    add("sales.today", "Today's sales", sales.today.sales, "INR")
    add("sales.today.orders", "Today's orders", sales.today.transactions, "orders")
    add("sales.7d", "Sales in last 7 days", sales.last_7_days.sales, "INR")
    add("sales.7d.orders", "Orders in last 7 days", sales.last_7_days.transactions, "orders")
    add("sales.7d.customers", "Unique customer references in last 7 days", sales.last_7_days.unique_customer_references, "references")
    add("sales.previous_7d", "Sales in previous 7 days", sales.previous_7_days.sales, "INR")
    if sales.growth_7_days_percent is not None:
        add("sales.growth_7d", "Sales change vs previous 7 days", sales.growth_7_days_percent, "%")
    add("sales.30d", "Sales in last 30 days", sales.last_30_days.sales, "INR")
    add("sales.30d.orders", "Orders in last 30 days", sales.last_30_days.transactions, "orders")
    add("sales.30d.customers", "Unique customer references in last 30 days", sales.last_30_days.unique_customer_references, "references")
    add("sales.previous_30d", "Sales in previous 30 days", sales.previous_30_days.sales, "INR")
    if sales.growth_30_days_percent is not None:
        add("sales.growth_30d", "Sales change vs previous 30 days", sales.growth_30_days_percent, "%")

    add("products.total", "Products in catalog", context.products.total_products, "products")
    add("products.categories", "Product categories", context.products.total_categories, "categories")
    add("inventory.total_units", "Current units in stock", context.inventory.total_units_in_stock, "units")
    add("inventory.low_stock_count", "Products at or below reorder threshold", context.inventory.low_stock_count, "products")
    add("inventory.stockout_count", "Out-of-stock products", context.inventory.stockout_count, "products")
    add("customers.unique_30d", "Unique customer references in last 30 days", context.customers.unique_customer_references_30_days, "references")
    add("customers.repeat_30d", "Repeat customer references in last 30 days", context.customers.repeat_customer_references_30_days, "references")

    performance_sets = (
        ("top30", context.products.top_selling_30_days),
        ("slow30", context.products.slow_moving_30_days),
        ("fast7", context.products.fast_moving_7_days),
    )
    for group_name, products in performance_sets:
        for product in products:
            prefix = f"product.{product.product_id}"
            add(f"{prefix}.{group_name}.units", f"{product.name} units sold ({group_name})", product.units_sold, "units")
            add(f"{prefix}.{group_name}.revenue", f"{product.name} revenue ({group_name})", product.revenue, "INR")

    risk_records = {
        risk.product_id: risk
        for risk in context.inventory.products_at_stockout_risk + context.inventory.fast_moving_low_stock_products
    }
    for risk in risk_records.values():
        prefix = f"product.{risk.product_id}.inventory"
        add(f"{prefix}.stock", f"{risk.name} current stock", risk.current_stock, "units")
        add(f"{prefix}.threshold", f"{risk.name} reorder threshold", risk.reorder_threshold, "units")
        add(f"{prefix}.sold7", f"{risk.name} units sold in last 7 days", risk.units_sold_7_days, "units")
        if risk.estimated_days_of_stock is not None:
            add(f"{prefix}.days_cover", f"{risk.name} estimated days of stock", risk.estimated_days_of_stock, "days")
    return metrics


def _rules_analysis(context: MerchantBusinessContext, evidence: dict[str, EvidenceMetric]) -> CopilotAnalysis:
    insights: list[CopilotInsight] = []
    opportunities: list[BusinessOpportunity] = list(context.opportunities)
    recommendations = build_recommendations(context)
    sales = context.sales
    inventory = context.inventory
    top_products = context.products.top_selling_30_days

    if sales.growth_7_days_percent is not None:
        direction = "increased" if sales.growth_7_days_percent > 0 else "declined" if sales.growth_7_days_percent < 0 else "was unchanged"
        insights.append(CopilotInsight(
            title=f"Seven-day sales {direction}",
            explanation=f"Recorded sales over the last seven days were {_format_money(sales.last_7_days.sales)} compared with {_format_money(sales.previous_7_days.sales)} in the previous seven-day period.",
            supporting_metrics=[evidence["sales.7d"], evidence["sales.previous_7d"], evidence["sales.growth_7d"]],
            severity="info" if sales.growth_7_days_percent >= 0 else "warning",
        ))
    else:
        insights.append(CopilotInsight(
            title="Sales comparison is not available yet",
            explanation="There are no recorded sales in the previous seven-day period to calculate a percentage change.",
            supporting_metrics=[evidence["sales.7d"], evidence["sales.previous_7d"]],
            severity="info",
        ))

    if inventory.low_stock_count or inventory.stockout_count:
        insights.append(CopilotInsight(
            title="Some grocery products need a stock check",
            explanation=f"{inventory.low_stock_count} products are at or below their reorder thresholds, including {inventory.stockout_count} out-of-stock products.",
            supporting_metrics=[evidence["inventory.low_stock_count"], evidence["inventory.stockout_count"]],
            severity="warning",
        ))
    else:
        insights.append(CopilotInsight(
            title="Current stock is above reorder thresholds",
            explanation="No products are currently at or below their configured reorder thresholds.",
            supporting_metrics=[evidence["inventory.low_stock_count"], evidence["inventory.stockout_count"]],
            severity="info",
        ))

    if top_products:
        leader = top_products[0]
        prefix = f"product.{leader.product_id}.top30"
        insights.append(CopilotInsight(
            title=f"{leader.name} leads recent product revenue",
            explanation=f"It recorded {_format_money(leader.revenue)} in revenue across {leader.units_sold} units over the last 30 days.",
            supporting_metrics=[evidence[f"{prefix}.revenue"], evidence[f"{prefix}.units"]],
            severity="info",
        ))

    if sales.last_30_days.transactions:
        summary = (
            f"{context.merchant.business_name} recorded {_format_money(sales.last_30_days.sales)} "
            f"across {sales.last_30_days.transactions} transactions in the last 30 days. "
            f"{inventory.low_stock_count} products need a stock check."
        )
        summary_metrics = [evidence["sales.30d"], evidence["sales.30d.orders"], evidence["inventory.low_stock_count"]]
    else:
        summary = f"No sales were recorded for {context.merchant.business_name} in the last 30 days. Add sales to build product and customer insights."
        summary_metrics = [evidence["sales.30d"], evidence["sales.30d.orders"]]
    if context.customers.repeat_customer_references_30_days:
        summary += f" {context.customers.repeat_customer_references_30_days} customer references have repeat purchases."
        summary_metrics.append(evidence["customers.repeat_30d"])

    return CopilotAnalysis(
        merchant_name=context.merchant.business_name,
        provider="grounded-rules",
        summary=summary,
        insights=insights,
        opportunities=opportunities,
        recommended_actions=recommendations[:5],
        generated_at=datetime.now(timezone.utc),
    )


def _resolve_provider_response(
    merchant_name: str,
    generated: ProviderAnalysis,
    evidence: dict[str, EvidenceMetric],
    opportunities: list[BusinessOpportunity],
    recommendations: list[CopilotRecommendation],
) -> CopilotAnalysis | None:
    def resolve(keys: list[str]) -> list[EvidenceMetric] | None:
        if not keys or any(key not in evidence for key in keys):
            return None
        return [evidence[key] for key in keys]

    all_text = [generated.summary]
    all_text.extend(text for item in generated.insights + generated.opportunities for text in (item.title, item.explanation))
    all_text.extend(text for item in generated.recommended_actions for text in (item.title, item.reason, item.expected_impact))
    if any(re.search(r"\d|[₹%]", text) for text in all_text):
        return None

    insights: list[CopilotInsight] = []
    for item in generated.insights:
        metrics = resolve(item.metric_keys)
        if metrics is None:
            return None
        insights.append(CopilotInsight(title=item.title, explanation=item.explanation, supporting_metrics=metrics, severity=item.severity))
    for item in generated.opportunities:
        metrics = resolve(item.metric_keys)
        if metrics is None:
            return None
    for item in generated.recommended_actions:
        metrics = resolve(item.metric_keys)
        if metrics is None:
            return None
    return CopilotAnalysis(
        merchant_name=merchant_name,
        provider="openai-compatible",
        summary=generated.summary,
        insights=insights,
        opportunities=opportunities,
        recommended_actions=recommendations[:5],
        generated_at=datetime.now(timezone.utc),
    )


def analyze_business(database: Session, merchant: Merchant, question: str | None = None) -> tuple[MerchantBusinessContext, CopilotAnalysis]:
    context = build_merchant_context(database, merchant)
    evidence = _evidence(context)
    grounded_result = _rules_analysis(context, evidence)
    try:
        provider = configured_provider()
    except AIProviderError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    if provider is None:
        return context, grounded_result
    try:
        generated = provider.analyze(context, sorted(evidence), question)
    except AIProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    validated = _resolve_provider_response(merchant.business_name, generated, evidence, context.opportunities, grounded_result.recommended_actions)
    return context, validated or grounded_result


def recommend_actions(database: Session, merchant: Merchant) -> RecommendationResponse:
    context = build_merchant_context(database, merchant)
    return RecommendationResponse(
        merchant_name=merchant.business_name,
        recommendations=build_recommendations(context),
        generated_at=datetime.now(timezone.utc),
    )
