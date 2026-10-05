from collections.abc import Generator
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import Merchant, Product, Transaction, TransactionItem


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)

    def override_database() -> Generator[Session, None, None]:
        database = test_session()
        try:
            yield database
        finally:
            database.close()

    app.dependency_overrides[get_db] = override_database
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def register(client: TestClient, email: str, business_name: str) -> str:
    response = client.post("/api/v1/auth/register", json={
        "businessName": business_name,
        "email": email,
        "password": "correct-horse-battery",
    })
    assert response.status_code == 201, response.text
    return response.json()["accessToken"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_product(client: TestClient, token: str, *, stock: int = 5) -> dict[str, object]:
    response = client.post("/api/v1/products", headers=auth(token), json={
        "name": "Basmati Rice 5 kg",
        "category": "Staples",
        "sku": "RICE-001",
        "unitPrice": "650.00",
        "costPrice": "510.00",
        "stockQuantity": stock,
        "lowStockThreshold": 2,
    })
    assert response.status_code == 201
    return response.json()


def test_authentication_is_required_for_merchant_data(client: TestClient) -> None:
    response = client.get("/api/v1/products")
    assert response.status_code == 401


def test_merchants_cannot_read_each_others_products(client: TestClient) -> None:
    first_token = register(client, "first@example.com", "First Fresh Mart")
    second_token = register(client, "second@example.com", "Second Fresh Mart")
    product = create_product(client, first_token)

    assert client.get("/api/v1/products", headers=auth(second_token)).json() == []
    response = client.get(f"/api/v1/products/{product['id']}", headers=auth(second_token))
    assert response.status_code == 404


def test_sale_and_stock_movement_commit_atomically(client: TestClient) -> None:
    token = register(client, "seller@example.com", "Seller Fresh Mart")
    product = create_product(client, token, stock=2)
    headers = auth(token)
    sale_url = "/api/v1/transactions"

    insufficient = client.post(sale_url, headers=headers, json={
        "items": [{"productId": product["id"], "quantity": 3}],
        "paymentMethod": "UPI",
    })
    assert insufficient.status_code == 409
    assert client.get(f"/api/v1/products/{product['id']}", headers=headers).json()["stockQuantity"] == 2
    assert client.get(sale_url, headers=headers).json() == []

    sale = client.post(sale_url, headers=headers, json={
        "items": [{"productId": product["id"], "quantity": 2}],
        "paymentMethod": "Cash",
        "customerReference": "walk-in-001",
    })
    assert sale.status_code == 201
    assert sale.json()["total"] == "1300.00"
    assert client.get(f"/api/v1/products/{product['id']}", headers=headers).json()["stockQuantity"] == 0
    inventory = client.get("/api/v1/inventory", headers=headers).json()
    sale_movement = next(item for item in inventory["movements"] if item["movementType"] == "sale")
    assert sale_movement["quantity"] == -2


def test_multi_item_sale_is_one_transaction_and_deducts_each_product(client: TestClient) -> None:
    token = register(client, "multi-item@example.com", "Multi Item Fresh Mart")
    headers = auth(token)
    first = create_product(client, token, stock=5)
    second_response = client.post("/api/v1/products", headers=headers, json={
        "name": "Masala packet",
        "category": "Spices",
        "sku": "MASALA-001",
        "unitPrice": "85.00",
        "costPrice": "60.00",
        "stockQuantity": 4,
        "lowStockThreshold": 2,
    })
    assert second_response.status_code == 201
    second = second_response.json()

    sale = client.post("/api/v1/transactions", headers=headers, json={
        "items": [
            {"productId": first["id"], "quantity": 2},
            {"productId": second["id"], "quantity": 1},
        ],
        "paymentMethod": "UPI",
        "customerReference": "walk-in-multi-1",
    })
    assert sale.status_code == 201
    assert sale.json()["total"] == "1385.00"
    assert len(sale.json()["items"]) == 2
    assert len(client.get("/api/v1/transactions", headers=headers).json()) == 1
    assert client.get(f"/api/v1/products/{first['id']}", headers=headers).json()["stockQuantity"] == 3
    assert client.get(f"/api/v1/products/{second['id']}", headers=headers).json()["stockQuantity"] == 3
    movements = client.get("/api/v1/inventory", headers=headers).json()["movements"]
    assert {movement["productId"]: movement["quantity"] for movement in movements if movement["movementType"] == "sale"} == {
        first["id"]: -2,
        second["id"]: -1,
    }


def test_today_transactions_filter_uses_merchant_local_day_and_newest_first(client: TestClient) -> None:
    token = register(client, "today-filter@example.com", "Today Filter Mart")
    headers = auth(token)
    product_data = create_product(client, token, stock=10)
    product_id = UUID(product_data["id"])
    local_today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    start_utc = datetime.combine(local_today, time.min, tzinfo=ZoneInfo("Asia/Kolkata")).astimezone(timezone.utc)
    transaction_times = [start_utc + timedelta(hours=9), start_utc + timedelta(hours=15), start_utc - timedelta(minutes=1)]

    session_generator = app.dependency_overrides[get_db]()
    database = next(session_generator)
    try:
        merchant = database.scalar(select(Merchant).where(Merchant.email == "today-filter@example.com"))
        for index, created_at in enumerate(transaction_times):
            transaction_id = uuid4()
            transaction = Transaction(
                id=transaction_id,
                merchant_id=merchant.id,
                total=Decimal("54.00"),
                payment_method="Cash",
                customer_reference=f"day-customer-{index}",
                created_at=created_at,
            )
            transaction.items.append(TransactionItem(
                id=uuid4(),
                product_id=product_id,
                product_name=product_data["name"],
                sku=product_data["sku"],
                quantity=1,
                unit_price=Decimal("54.00"),
                line_total=Decimal("54.00"),
            ))
            database.add(transaction)
        database.commit()
    finally:
        session_generator.close()

    response = client.get("/api/v1/transactions?today=true", headers=headers)
    assert response.status_code == 200
    today_sales = response.json()
    assert len(today_sales) == 2
    assert today_sales[0]["createdAt"] > today_sales[1]["createdAt"]
    assert {sale["customerReference"] for sale in today_sales} == {"day-customer-0", "day-customer-1"}
    assert len(client.get("/api/v1/transactions", headers=headers).json()) == 3


def test_inventory_adjustment_is_merchant_scoped(client: TestClient) -> None:
    first_token = register(client, "owner@example.com", "Owner Fresh Mart")
    second_token = register(client, "other@example.com", "Other Fresh Mart")
    product = create_product(client, first_token, stock=3)

    response = client.post(
        f"/api/v1/inventory/products/{product['id']}/restock",
        headers=auth(second_token),
        json={"quantity": 10, "reason": "Unauthorized restock"},
    )
    assert response.status_code == 404
    assert client.get(f"/api/v1/products/{product['id']}", headers=auth(first_token)).json()["stockQuantity"] == 3


def test_product_update_restock_count_and_delete_preserve_history(client: TestClient) -> None:
    token = register(client, "catalog@example.com", "Catalog Fresh Mart")
    headers = auth(token)
    product = create_product(client, token, stock=4)
    product_url = f"/api/v1/products/{product['id']}"

    updated = client.patch(product_url, headers=headers, json={
        "name": "Premium Basmati Rice 5 kg",
        "unitPrice": "675.00",
        "lowStockThreshold": 6,
    })
    assert updated.status_code == 200
    assert updated.json()["name"] == "Premium Basmati Rice 5 kg"

    restocked = client.post(
        f"/api/v1/inventory/products/{product['id']}/restock",
        headers=headers,
        json={"quantity": 3, "reason": "Supplier delivery"},
    )
    assert restocked.json()["stockQuantity"] == 7
    counted = client.post(
        f"/api/v1/inventory/products/{product['id']}/count",
        headers=headers,
        json={"stockQuantity": 2, "reason": "Damaged units removed"},
    )
    assert counted.json()["stockQuantity"] == 2
    assert client.patch(
        f"/api/v1/inventory/products/{product['id']}/threshold",
        headers=headers,
        json={"lowStockThreshold": 4},
    ).json()["lowStockThreshold"] == 4

    movements = client.get("/api/v1/inventory", headers=headers).json()["movements"]
    assert {movement["movementType"] for movement in movements} == {"opening", "restock", "adjustment"}
    assert client.delete(product_url, headers=headers).status_code == 204
    assert client.get("/api/v1/products", headers=headers).json() == []
    retained_history = client.get("/api/v1/inventory", headers=headers).json()["movements"]
    assert all(movement["productId"] is None for movement in retained_history)
    assert {movement["productName"] for movement in retained_history} == {"Basmati Rice 5 kg", "Premium Basmati Rice 5 kg"}


def _month_start(value: date, months_before: int = 0) -> date:
    month_index = value.year * 12 + value.month - 1 - months_before
    year, month_index = divmod(month_index, 12)
    return date(year, month_index + 1, 1)


def test_dashboard_period_aggregates_series_top_five_and_inventory_independently(client: TestClient) -> None:
    token = register(client, "periods@example.com", "Period Fresh Mart")
    headers = auth(token)
    products = [create_product(client, token, stock=2)]
    for index in range(2, 7):
        response = client.post("/api/v1/products", headers=headers, json={
            "name": f"Grocery item {index}",
            "category": "Staples",
            "sku": f"SKU-{index:03d}",
            "unitPrice": "650.00",
            "costPrice": "510.00",
            "stockQuantity": 2,
            "lowStockThreshold": 2,
        })
        assert response.status_code == 201
        products.append(response.json())

    now = datetime.now(timezone.utc)
    today_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    start_7d = today_start - timedelta(days=6)
    start_30d = today_start - timedelta(days=29)
    start_12m_day = _month_start(now.date(), 11)
    previous_12m_start = _month_start(start_12m_day, 12)
    current_sales = [100, 90, 80, 70, 60, 10]
    customer_refs = ["repeat-1", "repeat-2", "repeat-1", "repeat-2", "repeat-1", "repeat-2"]

    session_generator = app.dependency_overrides[get_db]()
    database = next(session_generator)
    try:
        merchant = database.scalar(select(Merchant).where(Merchant.email == "periods@example.com"))
        transaction_specs = [
            (current_sales[index], customer_refs[index], now - timedelta(days=1 + index % 2), products[index])
            for index in range(6)
        ]
        transaction_specs.extend([
            (40, "previous-7d-customer", start_7d - timedelta(days=1), products[0]),
            (200, "current-30d-customer", start_30d + timedelta(days=1), products[1]),
            (300, "previous-30d-customer", start_30d - timedelta(days=1), products[2]),
            (500, "previous-12m-customer", datetime.combine(previous_12m_start, time(12), tzinfo=timezone.utc), products[3]),
            (1000, "older-customer", datetime.combine(previous_12m_start - timedelta(days=1), time(12), tzinfo=timezone.utc), products[4]),
        ])
        for amount, customer_reference, created_at, product_data in transaction_specs:
            product_id = UUID(product_data["id"])
            transaction = Transaction(
                id=uuid4(),
                merchant_id=merchant.id,
                total=Decimal(amount),
                payment_method="UPI",
                customer_reference=customer_reference,
                created_at=created_at,
            )
            transaction.items.append(TransactionItem(
                id=uuid4(),
                product_id=product_id,
                product_name=product_data["name"],
                sku=product_data["sku"],
                quantity=1,
                unit_price=Decimal(amount),
                line_total=Decimal(amount),
            ))
            database.add(transaction)
        database.commit()
    finally:
        session_generator.close()

    seven = client.get("/api/v1/dashboard", headers=headers)
    assert seven.status_code == 200
    seven_data = seven.json()
    assert seven_data["period"] == "7d"
    assert seven_data["totalSales"] == "410.00"
    assert seven_data["totalOrders"] == 6
    assert seven_data["customers"] == 2
    assert seven_data["averageOrderValue"] == "68.33"
    assert seven_data["salesChangePercent"] == "925.00"
    assert len(seven_data["salesSeries"]) == 7
    assert len(seven_data["topProducts"]) == 5
    assert seven_data["topProducts"][-1]["revenue"] == "60.00"

    thirty = client.get("/api/v1/dashboard?period=30d", headers=headers)
    assert thirty.status_code == 200
    thirty_data = thirty.json()
    assert thirty_data["totalSales"] == "650.00"
    assert thirty_data["totalOrders"] == 8
    assert thirty_data["customers"] == 4
    assert thirty_data["salesChangePercent"] == "116.67"
    assert len(thirty_data["salesSeries"]) == 30

    twelve_months = client.get("/api/v1/dashboard?period=12m", headers=headers)
    assert twelve_months.status_code == 200
    twelve_data = twelve_months.json()
    assert twelve_data["totalSales"] == "950.00"
    assert twelve_data["totalOrders"] == 9
    assert twelve_data["customers"] == 5
    assert twelve_data["salesChangePercent"] == "90.00"
    assert len(twelve_data["salesSeries"]) == 12
    assert twelve_data["inventoryAlerts"] == seven_data["inventoryAlerts"]

    assert client.get("/api/v1/dashboard?period=all", headers=headers).status_code == 422


def test_dashboard_empty_period_returns_zero_metrics_and_granularity(client: TestClient) -> None:
    token = register(client, "empty-period@example.com", "Empty Period Mart")
    headers = auth(token)
    for period, point_count in (("7d", 7), ("30d", 30), ("12m", 12)):
        response = client.get(f"/api/v1/dashboard?period={period}", headers=headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["totalSales"] == "0.00"
        assert payload["totalOrders"] == 0
        assert payload["customers"] == 0
        assert payload["averageOrderValue"] == "0.00"
        assert payload["salesChangePercent"] is None
        assert len(payload["salesSeries"]) == point_count
        assert all(point["current"] == "0.00" and point["previous"] == "0.00" for point in payload["salesSeries"])
        assert payload["topProducts"] == []


def test_ai_copilot_context_and_analysis_are_merchant_scoped_and_evidence_backed(client: TestClient) -> None:
    first_token = register(client, "copilot-first@example.com", "First Grocery Mart")
    second_token = register(client, "copilot-second@example.com", "Second Grocery Mart")
    first_headers = auth(first_token)
    second_headers = auth(second_token)
    first_product = create_product(client, first_token, stock=1)
    second_product = create_product(client, second_token, stock=5)

    now = datetime.now(timezone.utc)
    session_generator = app.dependency_overrides[get_db]()
    database = next(session_generator)
    try:
        merchants = {merchant.email: merchant for merchant in database.scalars(select(Merchant)).all()}
        for merchant, product, total, reference in [
            (merchants["copilot-first@example.com"], first_product, Decimal("650.00"), "repeat-customer"),
            (merchants["copilot-first@example.com"], first_product, Decimal("650.00"), "repeat-customer"),
            (merchants["copilot-second@example.com"], second_product, Decimal("99999.00"), "other-customer"),
        ]:
            transaction = Transaction(
                id=uuid4(),
                merchant_id=merchant.id,
                total=total,
                payment_method="UPI",
                customer_reference=reference,
                created_at=now - timedelta(days=1),
            )
            transaction.items.append(TransactionItem(
                id=uuid4(),
                product_id=UUID(product["id"]),
                product_name=product["name"],
                sku=product["sku"],
                quantity=1,
                unit_price=total,
                line_total=total,
            ))
            database.add(transaction)
        database.commit()
    finally:
        session_generator.close()

    unauthorized = client.get("/api/v1/ai-copilot/context")
    assert unauthorized.status_code == 401

    context_response = client.get("/api/v1/ai-copilot/context", headers=first_headers)
    assert context_response.status_code == 200
    context = context_response.json()
    assert context["merchant"]["businessName"] == "First Grocery Mart"
    assert context["sales"]["last30Days"]["sales"] == "1300.00"
    assert context["sales"]["last30Days"]["transactions"] == 2
    assert context["customers"]["uniqueCustomerReferences30Days"] == 1
    assert context["customers"]["repeatCustomerReferences30Days"] == 1
    assert context["products"]["totalProducts"] == 1
    assert context["inventory"]["lowStockCount"] == 1
    assert all(product["productId"] != second_product["id"] for product in context["products"]["topSelling30Days"])

    analysis_response = client.post("/api/v1/ai-copilot/analyze", headers=first_headers, json={"question": "What should I restock?"})
    assert analysis_response.status_code == 200
    analysis = analysis_response.json()
    assert analysis["provider"] == "grounded-rules"
    assert analysis["merchantName"] == "First Grocery Mart"
    assert all(
        set(opportunity) == {"type", "severity", "title", "reason", "metrics", "recommendedAction"}
        for opportunity in analysis["opportunities"]
    )
    assert analysis["recommendedActions"]
    assert all(action["requiresConfirmation"] for action in analysis["recommendedActions"])
    assert all(metric["key"] and metric["value"] is not None for item in analysis["insights"] for metric in item["supportingMetrics"])

    recommendations_response = client.get("/api/v1/ai-copilot/recommendations", headers=first_headers)
    assert recommendations_response.status_code == 200
    recommendations_payload = recommendations_response.json()
    assert recommendations_payload["merchantName"] == "First Grocery Mart"
    assert recommendations_payload["recommendations"]
    recommendation = recommendations_payload["recommendations"][0]
    assert recommendation["whatIsHappening"]
    assert recommendation["whyItMatters"]
    assert recommendation["supportingNumbers"]
    assert recommendation["recommendedAction"]
    assert recommendation["expectedImpact"]
    assert recommendation["requiresApproval"] is True

    chat_response = client.post(
        "/api/v1/ai-copilot/chat",
        headers=first_headers,
        json={"message": "How is my business doing this week?"},
    )
    assert chat_response.status_code == 200
    chat_payload = chat_response.json()
    assert "1300.00" in chat_payload["answer"] or chat_payload["supportingMetrics"]
    assert all(metric["value"] is not None for metric in chat_payload["supportingMetrics"])

    compatibility_chat_response = client.post(
        "/api/ai-copilot/chat",
        headers=first_headers,
        json={"message": "Which products should I restock?"},
    )
    assert compatibility_chat_response.status_code == 200
    assert compatibility_chat_response.json()["answer"]

    query_expectations = [
        ("hi", "AI business partner", False),
        ("hello", "AI business partner", False),
        ("how are my sales?", "This week", True),
        ("what are my top products?", "top products", True),
        ("what should I restock?", "restock", True),
        ("which products are slow moving?", "slow", False),
        ("how can I increase sales?", "opportunity", True),
        ("how much did I sell today?", "Today", True),
        ("show me this month's sales", "This month", True),
        ("why did sales drop?", "sales", True),
        ("create a campaign", "campaign", False),
    ]
    answers: dict[str, str] = {}
    for query, expected_text, expect_metrics in query_expectations:
        response = client.post("/api/v1/ai-copilot/chat", headers=first_headers, json={"message": query})
        assert response.status_code == 200, query
        payload = response.json()
        answers[query] = payload["answer"]
        assert expected_text.lower() in payload["answer"].lower(), query
        if expect_metrics:
            assert payload["supportingMetrics"], query

    assert not answers["hi"].startswith("This week")
    assert not answers["hello"].startswith("This week")
    assert len(set(answers.values())) > 5
