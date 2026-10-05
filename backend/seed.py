import os
from datetime import datetime, timezone
from decimal import Decimal
from getpass import getpass

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Campaign, InventoryMovement, Merchant, Product, Transaction, TransactionItem


def sample_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def seed() -> None:
    email = os.environ.get("SEED_MERCHANT_EMAIL") or input("Seed merchant email: ").strip().lower()
    password = os.environ.get("SEED_MERCHANT_PASSWORD") or getpass("Seed merchant password (8+ characters): ")
    business_name = os.environ.get("SEED_BUSINESS_NAME", "Mehta Fresh Mart")
    if len(password) < 8:
        raise SystemExit("The seed merchant password must contain at least 8 characters.")

    with SessionLocal() as database:
        existing = database.scalar(select(Merchant).where(Merchant.email == email))
        if existing is not None:
            print(f"Seed data already exists for {existing.email}; no changes made.")
            return

        merchant = Merchant(business_name=business_name, email=email, password_hash=hash_password(password))
        database.add(merchant)
        database.flush()

        product_specs = [
            ("2048", "Whole Wheat Atta 5 kg", "Staples", "285.00", "218.00", 4, 8, 1),
            ("1182", "Basmati Rice 5 kg", "Staples", "649.00", "512.00", 42, 10, 3),
            ("3091", "Sunflower Oil 1 L", "Cooking essentials", "155.00", "121.00", 8, 10, 2),
            ("0876", "Full Cream Milk 1 L", "Dairy", "68.00", "52.00", 12, 15, 1),
        ]
        products_by_sku: dict[str, Product] = {}
        for sku, name, category, price, cost, stock, threshold, units_sold in product_specs:
            product = Product(
                merchant_id=merchant.id,
                name=name,
                category=category,
                sku=f"SKU {sku}",
                unit_price=Decimal(price),
                cost_price=Decimal(cost),
                stock_quantity=stock,
                low_stock_threshold=threshold,
            )
            database.add(product)
            database.flush()
            products_by_sku[sku] = product
            database.add(InventoryMovement(
                merchant_id=merchant.id,
                product_id=product.id,
                product_name=product.name,
                movement_type="opening",
                quantity=stock + units_sold,
                reason="Opening stock",
                created_at=sample_datetime("2026-09-01T08:00:00"),
            ))

        sale_specs = [
            ("2048", 1, "UPI", "customer-001", "2026-09-28T11:42:00"),
            ("1182", 1, "UPI", "customer-001", "2026-09-28T11:42:00"),
            ("1182", 2, "Net banking", "customer-002", "2026-09-27T13:21:00"),
            ("3091", 2, "Cash", "customer-003", "2026-09-28T09:50:00"),
            ("0876", 1, "UPI", "customer-002", "2026-09-27T16:05:00"),
        ]
        for sku, quantity, payment_method, customer_reference, sold_at in sale_specs:
            product = products_by_sku[sku]
            total = (product.unit_price * quantity).quantize(Decimal("0.01"))
            transaction = Transaction(
                merchant_id=merchant.id,
                total=total,
                payment_method=payment_method,
                customer_reference=customer_reference,
                created_at=sample_datetime(sold_at),
            )
            transaction.items.append(TransactionItem(
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                quantity=quantity,
                unit_price=product.unit_price,
                line_total=total,
            ))
            database.add(transaction)
            database.flush()
            database.add(InventoryMovement(
                merchant_id=merchant.id,
                product_id=product.id,
                product_name=product.name,
                movement_type="sale",
                quantity=-quantity,
                reason=f"Sale {transaction.id}",
                created_at=transaction.created_at,
            ))

        database.add_all([
            Campaign(merchant_id=merchant.id, name="Weekend fresh produce offer", channel="Paytm offers", status="active", reach="1,240 customers"),
            Campaign(merchant_id=merchant.id, name="Festive pantry savings", channel="Store promotion", status="scheduled", reach="Starts 4 Oct"),
            Campaign(merchant_id=merchant.id, name="Everyday staples offer", channel="Customer segment", status="draft", reach="86 customers"),
        ])
        database.commit()
        print(f"Seeded Mehta Fresh Mart with {len(products_by_sku)} grocery products and {len(sale_specs)} sales.")


if __name__ == "__main__":
    seed()