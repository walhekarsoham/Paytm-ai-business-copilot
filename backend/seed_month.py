import random
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models import InventoryMovement, Merchant, Product, Transaction, TransactionItem

SAMPLE_MARKER = "sample-month"


def seed_month(merchant_name: str = "Balaji Super Market", days: int = 30) -> None:
    if days < 1 or days > 90:
        raise ValueError("days must be between 1 and 90")

    today = datetime.now(timezone.utc).date()
    first_day = today - timedelta(days=days - 1)
    marker_prefix = f"{SAMPLE_MARKER}:{first_day.isoformat()}:"
    rng = random.Random(f"{merchant_name.casefold()}:{first_day.isoformat()}")

    with SessionLocal() as database:
        merchant = database.scalar(
            select(Merchant).where(func.lower(Merchant.business_name) == merchant_name.casefold())
        )
        if merchant is None:
            raise SystemExit(f"Merchant not found: {merchant_name}")

        existing_seed = database.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.merchant_id == merchant.id,
                Transaction.customer_reference.like(f"{marker_prefix}%"),
            )
        ) or 0
        if existing_seed:
            print(f"Monthly sample data already exists for {merchant.business_name} starting {first_day}.")
            return

        transaction_count = database.scalar(
            select(func.count(Transaction.id)).where(Transaction.merchant_id == merchant.id)
        ) or 0
        if transaction_count:
            raise SystemExit(
                f"{merchant.business_name} already has transactions. No records were changed to avoid mixing sample and real sales."
            )

        products = list(database.scalars(
            select(Product).where(Product.merchant_id == merchant.id).order_by(Product.id)
        ).all())
        if not products:
            raise SystemExit(f"{merchant.business_name} has no products. Add a grocery product before seeding sales.")

        opening_movements: dict[UUID, InventoryMovement] = {}
        for product in products:
            movements = list(database.scalars(
                select(InventoryMovement).where(
                    InventoryMovement.merchant_id == merchant.id,
                    InventoryMovement.product_id == product.id,
                )
            ).all())
            if len(movements) != 1 or movements[0].movement_type != "opening":
                raise SystemExit(
                    f"{product.name} has existing stock history beyond its opening balance. No records were changed."
                )
            opening_movements[product.id] = movements[0]

        daily_sales: dict[date, list[tuple[Product, int, str, datetime, str]]] = defaultdict(list)
        customer_count = 42
        for day_offset in range(days):
            sale_date = first_day + timedelta(days=day_offset)
            sale_count = rng.randint(3, 5)
            for _ in range(sale_count):
                product = rng.choice(products)
                quantity = rng.randint(1, 3)
                customer_number = rng.randint(1, customer_count)
                payment_method = rng.choice(("UPI", "UPI", "Cash", "Card"))
                sold_at = datetime.combine(
                    sale_date,
                    time(hour=rng.randint(7, 21), minute=rng.randint(0, 59)),
                    tzinfo=timezone.utc,
                )
                customer_reference = f"{marker_prefix}customer-{customer_number:03d}"
                daily_sales[sale_date].append((product, quantity, payment_method, sold_at, customer_reference))

        units_sold: dict[UUID, int] = defaultdict(int)
        units_sold_by_day: dict[date, dict[UUID, int]] = defaultdict(lambda: defaultdict(int))
        for sale_date, sales in daily_sales.items():
            for product, quantity, _, _, _ in sales:
                units_sold[product.id] += quantity
                units_sold_by_day[sale_date][product.id] += quantity

        for product in products:
            opening = opening_movements[product.id]
            opening.created_at = datetime.combine(first_day, time(6), tzinfo=timezone.utc)

        for block_start in range(0, days, 7):
            block_first_day = first_day + timedelta(days=block_start)
            block_last_day = min(block_first_day + timedelta(days=6), today)
            restock_time = datetime.combine(block_first_day, time(6, 30), tzinfo=timezone.utc)
            for product in products:
                restock_quantity = sum(
                    units_sold_by_day[sale_date].get(product.id, 0)
                    for sale_date in (block_first_day + timedelta(days=offset) for offset in range((block_last_day - block_first_day).days + 1))
                )
                if restock_quantity:
                    database.add(InventoryMovement(
                        merchant_id=merchant.id,
                        product_id=product.id,
                        product_name=product.name,
                        movement_type="restock",
                        quantity=restock_quantity,
                        reason=f"Sample month supplier restock ({first_day:%d %b}-{today:%d %b})",
                        created_at=restock_time,
                    ))

        transaction_total = Decimal("0.00")
        created_transactions = 0
        for sale_date in sorted(daily_sales):
            for product, quantity, payment_method, sold_at, customer_reference in daily_sales[sale_date]:
                line_total = (product.unit_price * quantity).quantize(Decimal("0.01"))
                transaction = Transaction(
                    merchant_id=merchant.id,
                    total=line_total,
                    payment_method=payment_method,
                    customer_reference=customer_reference,
                    created_at=sold_at,
                )
                transaction.items.append(TransactionItem(
                    product_id=product.id,
                    product_name=product.name,
                    sku=product.sku,
                    quantity=quantity,
                    unit_price=product.unit_price,
                    line_total=line_total,
                ))
                database.add(transaction)
                database.flush()
                database.add(InventoryMovement(
                    merchant_id=merchant.id,
                    product_id=product.id,
                    product_name=product.name,
                    movement_type="sale",
                    quantity=-quantity,
                    reason=f"Sample month sale {transaction.id}",
                    created_at=sold_at,
                ))
                transaction_total += line_total
                created_transactions += 1

        database.commit()
        print(
            f"Added {created_transactions} sample sales from {first_day} through {today} "
            f"for {merchant.business_name}; total sales ₹{transaction_total:,.2f}."
        )
        for product in products:
            database.refresh(product)
            print(f"{product.name}: {units_sold[product.id]} units sold; on-hand remains {product.stock_quantity}.")


if __name__ == "__main__":
    seed_month()