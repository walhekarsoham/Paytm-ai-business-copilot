from decimal import Decimal

from app.ai_copilot.schemas import BusinessOpportunity, MerchantBusinessContext, OpportunitySeverity


def _severity_for_drop(drop_percent: Decimal) -> OpportunitySeverity:
    if drop_percent >= Decimal("35"):
        return "critical"
    if drop_percent >= Decimal("20"):
        return "warning"
    return "opportunity"


def detect_opportunities(context: MerchantBusinessContext) -> list[BusinessOpportunity]:
    opportunities: list[BusinessOpportunity] = []
    sales = context.sales

    if sales.growth_7_days_percent is not None and sales.growth_7_days_percent <= Decimal("-15"):
        drop = abs(sales.growth_7_days_percent)
        opportunities.append(BusinessOpportunity(
            type="SALES_DROP",
            severity=_severity_for_drop(drop),
            title="Sales dropped versus the previous week",
            reason=(
                "Last 7 day revenue is materially below the previous equivalent period, "
                "which may indicate weaker demand, availability issues, or fewer repeat purchases."
            ),
            metrics={
                "current_revenue": sales.last_7_days.sales,
                "previous_revenue": sales.previous_7_days.sales,
                "growth_percent": sales.growth_7_days_percent,
                "current_transactions": sales.last_7_days.transactions,
                "previous_transactions": sales.previous_7_days.transactions,
            },
            recommended_action="Review daily sales, stockouts, and top category movement before changing pricing or promotions.",
        ))

    if (
        sales.last_30_days.transactions >= 5
        and sales.last_30_days.average_order_value < Decimal("150")
    ):
        opportunities.append(BusinessOpportunity(
            type="LOW_AVERAGE_ORDER_VALUE",
            severity="opportunity",
            title="Average order value is low",
            reason="Recent orders are frequent enough to measure, but the average basket value is below the target threshold.",
            metrics={
                "average_order_value": sales.last_30_days.average_order_value,
                "transactions": sales.last_30_days.transactions,
                "revenue": sales.last_30_days.sales,
            },
            recommended_action="Bundle complementary products or suggest add-ons at checkout to lift basket size.",
        ))

    for product in context.products.growing_products_30_days[:3]:
        if product.growth_percent is not None and product.growth_percent >= Decimal("50") and product.units_sold >= 3:
            opportunities.append(BusinessOpportunity(
                type="HIGH_GROWTH_PRODUCT",
                severity="opportunity",
                title=f"{product.name} is growing quickly",
                reason="The product's 30 day revenue grew sharply compared with the previous 30 days.",
                metrics={
                    "product_id": str(product.product_id),
                    "product_name": product.name,
                    "current_revenue": product.revenue,
                    "previous_revenue": product.previous_revenue,
                    "growth_percent": product.growth_percent,
                    "units_sold": product.units_sold,
                },
                recommended_action="Keep this item visible and make sure replenishment matches the new demand level.",
            ))

    for product in context.products.top_selling_30_days[:3]:
        if product.units_sold >= 5 and product.revenue_contribution_percent >= Decimal("20"):
            opportunities.append(BusinessOpportunity(
                type="POPULAR_PRODUCT",
                severity="opportunity",
                title=f"{product.name} is a popular product",
                reason="This product contributes a meaningful share of recent revenue and unit sales.",
                metrics={
                    "product_id": str(product.product_id),
                    "product_name": product.name,
                    "units_sold": product.units_sold,
                    "revenue": product.revenue,
                    "revenue_contribution_percent": product.revenue_contribution_percent,
                },
                recommended_action="Keep higher safety stock so this product stays available during demand spikes.",
            ))

    for risk in context.inventory.fast_moving_low_stock_products[:3]:
        opportunities.append(BusinessOpportunity(
            type="LOW_STOCK_FAST_MOVER",
            severity="critical" if risk.current_stock == 0 else "warning",
            title=f"{risk.name} may run out soon",
            reason="This product is moving in recent sales and is already at a low-stock or stockout-risk level.",
            metrics={
                "product_id": str(risk.product_id),
                "product_name": risk.name,
                "current_stock": risk.current_stock,
                "reorder_threshold": risk.reorder_threshold,
                "units_sold_7_days": risk.units_sold_7_days,
                "estimated_days_of_stock": str(risk.estimated_days_of_stock) if risk.estimated_days_of_stock is not None else "",
            },
            recommended_action="Confirm supplier availability and restock before the next demand peak.",
        ))

    for product in context.inventory.excess_or_slow_moving_products[:3]:
        opportunities.append(BusinessOpportunity(
            type="SLOW_MOVING_PRODUCT",
            severity="opportunity",
            title=f"{product.name} has slow inventory movement",
            reason="Current stock is high relative to recorded demand over the last 30 days.",
            metrics={
                "product_id": str(product.product_id),
                "product_name": product.name,
                "current_stock": product.current_stock,
                "units_sold_30_days": product.units_sold_30_days,
                "estimated_days_of_stock": str(product.estimated_days_of_stock) if product.estimated_days_of_stock is not None else "",
            },
            recommended_action="Review shelf placement, reduce reorder quantity, or run a small promotion with merchant approval.",
        ))

    for category in context.products.category_performance_30_days:
        if category.growth_percent is not None and category.growth_percent <= Decimal("-20") and category.revenue > 0:
            opportunities.append(BusinessOpportunity(
                type="CATEGORY_DECLINE",
                severity="warning",
                title=f"{category.category} category is declining",
                reason="Category revenue is down materially versus the previous 30 day period.",
                metrics={
                    "category": category.category,
                    "current_revenue": category.revenue,
                    "previous_revenue": category.previous_revenue,
                    "growth_percent": category.growth_percent,
                    "units_sold": category.units_sold,
                },
                recommended_action="Check whether key items in this category were unavailable, misplaced, or under-promoted.",
            ))
        if category.growth_percent is not None and category.growth_percent >= Decimal("35") and category.revenue > 0:
            opportunities.append(BusinessOpportunity(
                type="CATEGORY_GROWTH",
                severity="opportunity",
                title=f"{category.category} category is growing",
                reason="Category revenue is up strongly versus the previous 30 day period.",
                metrics={
                    "category": category.category,
                    "current_revenue": category.revenue,
                    "previous_revenue": category.previous_revenue,
                    "growth_percent": category.growth_percent,
                    "units_sold": category.units_sold,
                },
                recommended_action="Feature winning products in this category and protect stock for the fastest movers.",
            ))

    if context.customers.repeat_customer_references_30_days >= 3:
        opportunities.append(BusinessOpportunity(
            type="REPEAT_CUSTOMER_OPPORTUNITY",
            severity="opportunity",
            title="Repeat customers are identifiable",
            reason="Multiple customer references purchased more than once in the last 30 days.",
            metrics={
                "repeat_customer_references": context.customers.repeat_customer_references_30_days,
                "unique_customer_references": context.customers.unique_customer_references_30_days,
                "purchase_frequency": context.customers.purchase_frequency_30_days,
                "average_customer_transaction_value": context.customers.average_customer_transaction_value_30_days,
            },
            recommended_action="Create a merchant-approved repeat-customer offer for high-frequency shoppers.",
        ))

    return opportunities
