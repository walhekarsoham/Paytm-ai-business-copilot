from datetime import datetime, timezone

from app.ai_copilot.schemas import CopilotRecommendation, MerchantBusinessContext, RecommendationResponse


def _confidence(opportunity_type: str, severity: str) -> float:
    base_by_type = {
        "LOW_STOCK_FAST_MOVER": 0.9,
        "POPULAR_PRODUCT": 0.84,
        "HIGH_GROWTH_PRODUCT": 0.82,
        "SALES_DROP": 0.76,
        "LOW_AVERAGE_ORDER_VALUE": 0.72,
        "SLOW_MOVING_PRODUCT": 0.68,
        "CATEGORY_DECLINE": 0.66,
        "CATEGORY_GROWTH": 0.64,
        "REPEAT_CUSTOMER_OPPORTUNITY": 0.7,
    }
    severity_boost = {"critical": 0.04, "warning": 0.02, "opportunity": 0, "info": -0.04}
    return min(0.95, max(0.45, base_by_type.get(opportunity_type, 0.6) + severity_boost.get(severity, 0)))


def _recommendation_for_opportunity(opportunity) -> CopilotRecommendation:
    metrics = dict(opportunity.metrics)
    product_name = str(metrics.get("product_name", "the product"))
    category = str(metrics.get("category", "the category"))

    templates = {
        "LOW_STOCK_FAST_MOVER": {
            "title": f"Restock {product_name}",
            "what": f"{product_name} is selling quickly while current stock is low.",
            "why": "Fast-moving low-stock items can become unavailable before the next demand peak.",
            "action": f"Approve a restock review for {product_name} before the next busy period.",
            "impact": "Reduce stockout risk and protect availability for existing demand.",
            "action_type": "RESTOCK_PRODUCT",
        },
        "SALES_DROP": {
            "title": "Review a short promotion",
            "what": "Sales are down compared with the previous equivalent period.",
            "why": "A sales drop can point to weaker demand, fewer repeat visits, or product availability issues.",
            "action": "Approve a targeted promotion or campaign after checking stock on key products.",
            "impact": "Qualitatively, this can help recover demand while you investigate the cause of the drop.",
            "action_type": "CREATE_PROMOTION",
        },
        "SLOW_MOVING_PRODUCT": {
            "title": f"Bundle or discount {product_name}",
            "what": f"{product_name} has slow movement relative to current stock.",
            "why": "Slow-moving inventory ties up shelf space and cash that could support faster-moving items.",
            "action": f"Approve a small discount, bundle, or shelf-placement test for {product_name}.",
            "impact": "Qualitatively, this can improve sell-through without relying on an unproven revenue estimate.",
            "action_type": "CREATE_PROMOTION",
        },
        "HIGH_GROWTH_PRODUCT": {
            "title": f"Increase stock planning for {product_name}",
            "what": f"{product_name} is growing strongly versus the previous period.",
            "why": "Growth can turn into missed sales if replenishment does not keep up with demand.",
            "action": f"Approve higher replenishment planning for {product_name}.",
            "impact": "Protect availability for a product with proven recent momentum.",
            "action_type": "RESTOCK_PRODUCT",
        },
        "LOW_AVERAGE_ORDER_VALUE": {
            "title": "Create basket-building bundles",
            "what": "Average order value is below the configured threshold.",
            "why": "Low basket value means shoppers may be buying only one or two items per visit.",
            "action": "Approve product bundles or cross-sell prompts around commonly paired items.",
            "impact": "Qualitatively, this can encourage larger baskets without inventing a revenue forecast.",
            "action_type": "CREATE_BUNDLE",
        },
        "POPULAR_PRODUCT": {
            "title": f"Keep higher safety stock for {product_name}",
            "what": f"{product_name} is contributing a strong share of recent sales.",
            "why": "Popular products deserve a buffer because stockouts can affect customer trust and repeat visits.",
            "action": f"Approve a higher safety-stock target for {product_name}.",
            "impact": "Improve availability for a product customers are already buying.",
            "action_type": "RESTOCK_PRODUCT",
        },
        "CATEGORY_DECLINE": {
            "title": f"Investigate {category} decline",
            "what": f"{category} revenue is declining versus the previous period.",
            "why": "Category declines can be caused by missing items, weak visibility, or reduced customer demand.",
            "action": f"Review stock, pricing, and promotion coverage for {category}.",
            "impact": "Qualitatively, this can identify the cause before committing to a larger campaign.",
            "action_type": "REVIEW_SALES",
        },
        "CATEGORY_GROWTH": {
            "title": f"Feature {category} winners",
            "what": f"{category} revenue is growing versus the previous period.",
            "why": "Growing categories can benefit from better visibility and protected inventory.",
            "action": f"Approve extra visibility for top items in {category}.",
            "impact": "Support existing momentum without inventing future revenue.",
            "action_type": "CREATE_PROMOTION",
        },
        "REPEAT_CUSTOMER_OPPORTUNITY": {
            "title": "Create a repeat-customer offer",
            "what": "Repeat customer references are identifiable in recent sales.",
            "why": "Repeat shoppers are often the best audience for targeted, approval-led offers.",
            "action": "Approve a small repeat-customer campaign or loyalty-style offer.",
            "impact": "Encourage return visits from customers who have already purchased more than once.",
            "action_type": "CREATE_PROMOTION",
        },
    }
    template = templates.get(opportunity.type, {
        "title": opportunity.title,
        "what": opportunity.reason,
        "why": "The opportunity is backed by merchant data.",
        "action": opportunity.recommended_action,
        "impact": "Review the opportunity before taking action.",
        "action_type": "REVIEW_SALES",
    })
    return CopilotRecommendation(
        title=template["title"],
        opportunity_type=opportunity.type,
        what_is_happening=template["what"],
        why_it_matters=template["why"],
        reason=template["what"],
        explanation=template["why"],
        supporting_numbers=metrics,
        metrics=metrics,
        recommended_action=template["action"],
        expected_impact=template["impact"],
        confidence=_confidence(opportunity.type, opportunity.severity),
        action_type=template["action_type"],
        action=template["action"],
        requires_approval=True,
        requires_confirmation=True,
    )


def build_recommendations(context: MerchantBusinessContext) -> list[CopilotRecommendation]:
    recommendations = [_recommendation_for_opportunity(opportunity) for opportunity in context.opportunities]
    recommendations.sort(key=lambda item: (item.confidence, item.opportunity_type or ""), reverse=True)
    return recommendations[:8]


def build_recommendation_response(context: MerchantBusinessContext) -> RecommendationResponse:
    return RecommendationResponse(
        merchant_name=context.merchant.business_name,
        recommendations=build_recommendations(context),
        generated_at=datetime.now(timezone.utc),
    )
