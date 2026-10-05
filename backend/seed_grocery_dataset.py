"""Seed a repeat-safe 30-day synthetic grocery dataset for an existing merchant.

This uses only entities/fields from app.models. Synthetic customers are represented
by transaction.customer_reference because the current schema has no Customer table.
Unit sizes are embedded in product names because Product has no unit field. Taxes,
discount columns, and supplier purchase documents are also absent from this schema.
"""

import argparse
import hashlib
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models import Campaign, InventoryMovement, Merchant, Product, Transaction, TransactionItem

UTC = timezone.utc
IST = timezone(timedelta(hours=5, minutes=30))
OLD_SAMPLE_PREFIX = "sample-month:"
SAMPLE_PREFIX = "SYN30-GROCERY"
TARGET_PRODUCTS = 120
TARGET_TRANSACTIONS = 1_000


@dataclass(frozen=True)
class ProductSpec:
    name: str
    category: str
    sku: str
    price: Decimal
    popularity: float
    threshold: int
    cost_ratio: float


def _items(category_code: str, category: str, rows: list[tuple[str, str, str, float]]) -> list[ProductSpec]:
    specs: list[ProductSpec] = []
    for index, (base_name, unit, price_text, popularity) in enumerate(rows, start=1):
        sku = "DAL -001" if base_name == "Toor dal" else f"SYN-{category_code}-{index:03d}"
        name = base_name if base_name == "Toor dal" else f"{base_name} ({unit})"
        price = Decimal(price_text).quantize(Decimal("0.01"))
        threshold = 5 if category in {"Dairy & bakery", "Fresh produce", "Frozen & ready-to-eat"} else 12
        ratio = 0.77 if category in {"Staples & grains", "Pulses & beans"} else 0.72
        if category in {"Household essentials", "Personal care"}:
            ratio = 0.68
        specs.append(ProductSpec(name, category, sku, price, popularity, threshold, ratio))
    return specs


PRODUCT_SPECS = [
    *_items("GRN", "Staples & grains", [
        ("Basmati rice", "1 kg", "125", 1.35), ("Basmati rice", "5 kg", "590", 0.75),
        ("Sona Masoori rice", "1 kg", "74", 1.5), ("Ponni rice", "5 kg", "345", 0.85),
        ("Whole wheat atta", "5 kg", "285", 1.65), ("Multigrain atta", "5 kg", "365", 0.55),
        ("Maida", "1 kg", "58", 0.8), ("Poha", "500 g", "48", 1.05),
        ("Suji", "500 g", "43", 0.9), ("Rolled oats", "500 g", "148", 0.65),
    ]),
    *_items("PLS", "Pulses & beans", [
        ("Toor dal", "1 kg", "54", 1.6), ("Moong dal", "1 kg", "138", 1.15),
        ("Chana dal", "1 kg", "92", 1.1), ("Masoor dal", "1 kg", "110", 0.95),
        ("Urad dal", "1 kg", "145", 0.72), ("Rajma", "1 kg", "155", 0.8),
        ("Kabuli chana", "1 kg", "135", 0.7), ("Black chana", "1 kg", "88", 0.75),
        ("Green moong", "1 kg", "105", 0.68), ("Roasted gram", "500 g", "70", 0.6),
    ]),
    *_items("DAI", "Dairy & bakery", [
        ("Toned milk", "500 ml", "32", 1.8), ("Full cream milk", "500 ml", "36", 1.35),
        ("Fresh curd", "400 g", "43", 1.1), ("Paneer", "200 g", "105", 0.75),
        ("Salted butter", "100 g", "58", 0.72), ("Cheese slices", "200 g", "145", 0.6),
        ("White bread", "loaf", "40", 1.25), ("Multigrain bread", "loaf", "65", 0.45),
        ("Farm eggs", "12 pcs", "96", 1.3), ("Pure ghee", "500 ml", "330", 0.55),
    ]),
    *_items("PKG", "Packaged foods & snacks", [
        ("Glucose biscuits", "250 g", "35", 1.15), ("Cream biscuits", "200 g", "40", 0.95),
        ("Instant noodles", "pack of 4", "64", 1.55), ("Potato chips", "large pack", "40", 1.35),
        ("Masala namkeen", "250 g", "58", 1.05), ("Rusk", "300 g", "55", 0.72),
        ("Corn flakes", "500 g", "185", 0.62), ("Chocolate cookies", "200 g", "75", 0.78),
        ("Soya chunks", "200 g", "48", 0.66), ("Instant oats", "400 g", "125", 0.7),
    ]),
    *_items("SPI", "Spices & cooking essentials", [
        ("Refined sugar", "1 kg", "48", 1.35), ("Iodized salt", "1 kg", "30", 1.2),
        ("Sunflower oil", "1 L", "155", 1.5), ("Groundnut oil", "1 L", "190", 0.78),
        ("Turmeric powder", "100 g", "60", 0.75), ("Red chilli powder", "100 g", "72", 0.82),
        ("Garam masala", "100 g", "85", 0.68), ("Cumin seeds", "100 g", "70", 0.6),
        ("Coriander powder", "100 g", "62", 0.67), ("Mustard seeds", "100 g", "42", 0.58),
    ]),
    *_items("BEV", "Beverages", [
        ("Assam tea", "250 g", "160", 1.0), ("Instant coffee", "100 g", "135", 0.72),
        ("Cola", "750 ml", "40", 1.2), ("Cola", "2 L", "95", 0.8),
        ("Orange juice", "1 L", "120", 0.58), ("Mango drink", "1 L", "110", 0.8),
        ("Packaged drinking water", "1 L", "20", 0.95), ("Green tea", "25 bags", "145", 0.4),
        ("Energy drink", "250 ml", "110", 0.32), ("Spiced buttermilk", "200 ml", "20", 0.72),
    ]),
    *_items("PRO", "Fresh produce", [
        ("Potatoes", "1 kg", "32", 1.7), ("Onions", "1 kg", "38", 1.65),
        ("Tomatoes", "1 kg", "42", 1.5), ("Bananas", "1 dozen", "55", 1.15),
        ("Apples", "1 kg", "180", 0.55), ("Spinach", "1 bunch", "25", 0.6),
        ("Green chillies", "250 g", "25", 0.65), ("Lemons", "4 pcs", "30", 0.7),
        ("Carrots", "1 kg", "45", 0.68), ("Coriander leaves", "1 bunch", "15", 0.75),
    ]),
    *_items("HOU", "Household essentials", [
        ("Laundry detergent", "1 kg", "145", 0.8), ("Dishwash bar", "200 g", "25", 0.75),
        ("Dishwashing liquid", "500 ml", "105", 0.7), ("Bathing soap", "125 g", "38", 1.05),
        ("Toilet cleaner", "500 ml", "105", 0.48), ("Floor cleaner", "1 L", "145", 0.5),
        ("Facial tissues", "100 pulls", "65", 0.52), ("Kitchen scrubber", "2 pcs", "30", 0.5),
        ("Garbage bags", "30 pcs", "90", 0.36), ("Disinfectant cleaner", "500 ml", "85", 0.4),
    ]),
    *_items("PER", "Personal care", [
        ("Daily care shampoo", "180 ml", "145", 0.55), ("Herbal toothpaste", "150 g", "115", 0.82),
        ("Soft toothbrush", "1 pc", "35", 0.7), ("Coconut hair oil", "200 ml", "95", 0.55),
        ("Body wash", "250 ml", "175", 0.4), ("Gentle face wash", "100 ml", "135", 0.42),
        ("Sanitary pads", "8 pcs", "115", 0.65), ("Shaving cream", "70 g", "95", 0.32),
        ("Deodorant", "150 ml", "195", 0.35), ("Liquid handwash refill", "750 ml", "135", 0.5),
    ]),
    *_items("DFC", "Dry fruits & confectionery", [
        ("California almonds", "250 g", "260", 0.38), ("Whole cashews", "250 g", "290", 0.34),
        ("Golden raisins", "250 g", "105", 0.36), ("Seedless dates", "500 g", "180", 0.3),
        ("Roasted peanuts", "500 g", "95", 0.52), ("Milk chocolate bar", "50 g", "45", 0.82),
        ("Assorted chocolates", "160 g", "180", 0.35), ("Fruit toffee jar", "250 g", "125", 0.38),
        ("Peanut chikki", "200 g", "75", 0.42), ("Trail mix", "200 g", "220", 0.22),
    ]),
    *_items("FRZ", "Frozen & ready-to-eat", [
        ("Frozen green peas", "500 g", "85", 0.42), ("Frozen french fries", "500 g", "125", 0.35),
        ("Frozen parathas", "pack of 5", "115", 0.38), ("Vegetable momos", "pack of 12", "160", 0.25),
        ("Paneer tikka bites", "200 g", "180", 0.2), ("Vanilla ice cream", "500 ml", "170", 0.42),
        ("Malai kulfi", "pack of 4", "100", 0.32), ("Idli dosa batter", "1 kg", "90", 0.5),
        ("Instant soup", "pack of 4", "95", 0.28), ("Vegetable burger patties", "pack of 4", "135", 0.23),
    ]),
    *_items("BAB", "Baby & kitchen essentials", [
        ("Aluminium foil", "9 m", "90", 0.45), ("Cling film", "20 m", "75", 0.38),
        ("Paper cups", "25 pcs", "45", 0.3), ("Paper napkins", "100 pcs", "50", 0.4),
        ("Reusable zipper bags", "20 pcs", "75", 0.25), ("Baby diapers", "pack of 10", "250", 0.38),
        ("Baby wipes", "72 pcs", "115", 0.42), ("Baby shampoo", "100 ml", "120", 0.2),
        ("Baby cereal", "300 g", "265", 0.25), ("Baby lotion", "100 ml", "145", 0.2),
    ]),
]

CATEGORY_WEIGHTS = {
    "Staples & grains": 1.45,
    "Pulses & beans": 1.2,
    "Dairy & bakery": 1.25,
    "Packaged foods & snacks": 1.25,
    "Spices & cooking essentials": 1.05,
    "Beverages": 0.9,
    "Fresh produce": 1.15,
    "Household essentials": 0.62,
    "Personal care": 0.52,
    "Dry fruits & confectionery": 0.5,
    "Frozen & ready-to-eat": 0.38,
    "Baby & kitchen essentials": 0.38,
}


@dataclass
class PlannedLine:
    product: Product
    quantity: int
    unit_price: Decimal


@dataclass
class PlannedSale:
    sequence: int
    created_at: datetime
    payment_method: str
    customer_reference: str
    lines: list[PlannedLine]


def _stable_uuid(namespace: UUID, value: str) -> UUID:
    return uuid5(namespace, value)


def _daily_transaction_counts(first_day: date, days: int, target: int, rng: random.Random) -> list[int]:
    weights = []
    for offset in range(days):
        current_day = first_day + timedelta(days=offset)
        weekend_boost = 1.35 if current_day.weekday() >= 5 else 1.0
        weights.append(weekend_boost * rng.uniform(0.88, 1.12))
    raw = [target * weight / sum(weights) for weight in weights]
    counts = [int(value) for value in raw]
    remainder = target - sum(counts)
    for index in sorted(range(days), key=lambda item: raw[item] - counts[item], reverse=True)[:remainder]:
        counts[index] += 1
    return counts


def _weighted_product(rng: random.Random, products: list[Product], weights: dict[UUID, float]) -> Product:
    total = sum(weights[product.id] for product in products)
    position = rng.random() * total
    for product in products:
        position -= weights[product.id]
        if position <= 0:
            return product
    return products[-1]


def _transaction_time(rng: random.Random, current_day: date, latest_time: datetime | None = None) -> datetime:
    hours = list(range(7, 22))
    weights = [1, 2, 3, 4, 4, 3, 2, 2, 2, 3, 5, 6, 7, 6, 3]
    if latest_time is not None:
        last_hour = max(7, min(21, latest_time.hour))
        hours = list(range(7, last_hour + 1))
        weights = weights[:len(hours)]
    hour = rng.choices(hours, weights=weights, k=1)[0]
    latest_minute = latest_time.minute if latest_time is not None and hour == latest_time.hour else 59
    candidate = datetime.combine(current_day, time(hour, rng.randint(0, latest_minute), rng.randrange(60)), tzinfo=IST)
    if latest_time is not None and candidate > latest_time:
        return latest_time - timedelta(seconds=1)
    return candidate


def _build_sales(
    merchant: Merchant,
    products: list[Product],
    weights: dict[UUID, float],
    first_day: date,
    days: int,
    transaction_count: int,
    batch_marker: str,
    rng: random.Random,
    now_ist: datetime,
) -> list[PlannedSale]:
    customer_ids = list(range(1, 181))
    customer_weights = [6.0 if number <= 15 else 3.0 if number <= 55 else 1.0 for number in customer_ids]
    customer_choices = [f"{batch_marker}:CUSTOMER-{number:04d}" for number in customer_ids]
    # The first transaction for each customer makes the synthetic customer count deterministic.
    coverage = products.copy()
    rng.shuffle(coverage)
    day_counts = _daily_transaction_counts(first_day, days, transaction_count, rng)
    sales: list[PlannedSale] = []
    transaction_index = 0
    for day_offset, daily_count in enumerate(day_counts):
        current_day = first_day + timedelta(days=day_offset)
        for _ in range(daily_count):
            weekend = current_day.weekday() >= 5
            basket_roll = rng.random()
            if basket_roll < 0.11:
                item_count = 1
            elif basket_roll < 0.78:
                item_count = rng.randint(2, 5 if not weekend else 6)
            elif basket_roll < 0.97:
                item_count = rng.randint(6, 9)
            else:
                item_count = rng.randint(10, 14)
            item_count = min(item_count, len(products))
            chosen: list[Product] = []
            if transaction_index < len(coverage):
                chosen.append(coverage[transaction_index])
            while len(chosen) < item_count:
                candidate = _weighted_product(rng, [product for product in products if product not in chosen], weights)
                chosen.append(candidate)
            if transaction_index < len(customer_choices):
                customer_reference = customer_choices[transaction_index]
            else:
                customer_reference = rng.choices(customer_choices, weights=customer_weights, k=1)[0]
            payment_method = rng.choices(["UPI", "Cash", "Card"], weights=[64, 27, 9], k=1)[0]
            lines = [PlannedLine(product, rng.choices([1, 2, 3], weights=[76, 20, 4], k=1)[0], product.unit_price) for product in chosen]
            cutoff = now_ist if current_day == now_ist.date() else None
            sales.append(PlannedSale(transaction_index + 1, _transaction_time(rng, current_day, cutoff), payment_method, customer_reference, lines))
            transaction_index += 1
    return sales


def _seed(merchant_name: str, days: int, transaction_count: int, dry_run: bool = False) -> None:
    if days != 30:
        raise SystemExit("This dataset is designed for exactly 30 days.")
    if not 800 <= transaction_count <= 1_500:
        raise SystemExit("transactions must be between 800 and 1,500.")

    now_ist = datetime.now(IST)
    today = now_ist.date()
    first_day = today - timedelta(days=days - 1)
    batch_marker = f"{SAMPLE_PREFIX}-{first_day:%Y%m%d}"
    rng_seed = int(hashlib.sha256(f"{merchant_name.casefold()}:{batch_marker}".encode()).hexdigest()[:16], 16)
    rng = random.Random(rng_seed)

    database = SessionLocal()
    try:
        merchants = list(database.scalars(
            select(Merchant).where(func.lower(Merchant.business_name) == merchant_name.casefold())
        ).all())
        if len(merchants) != 1:
            raise SystemExit(f"Expected exactly one merchant named {merchant_name}; found {len(merchants)}.")
        merchant = merchants[0]
        merchant_namespace = merchant.id

        existing_batch = database.scalar(select(func.count(Transaction.id)).where(
            Transaction.merchant_id == merchant.id,
            Transaction.customer_reference.like(f"{batch_marker}:%"),
        )) or 0
        if existing_batch:
            future_transactions = list(database.scalars(select(Transaction).where(
                Transaction.merchant_id == merchant.id,
                Transaction.customer_reference.like(f"{batch_marker}:%"),
                Transaction.created_at > now_ist,
            )).all())
            for index, transaction in enumerate(future_transactions, start=1):
                safe_timestamp = now_ist - timedelta(seconds=index)
                transaction.created_at = safe_timestamp
                matching_movement = database.scalars(select(InventoryMovement).where(
                    InventoryMovement.merchant_id == merchant.id,
                    InventoryMovement.reason == f"SYNTHETIC {batch_marker} sale {transaction.id}",
                )).all()
                for movement in matching_movement:
                    movement.created_at = safe_timestamp
            if future_transactions:
                database.commit()
                print(f"Corrected {len(future_transactions)} future-dated synthetic transactions and their sale movements for {batch_marker}.")
            else:
                print(f"Dataset {batch_marker} already exists for {merchant.business_name}; no changes made.")
            return

        old_sample_transactions = list(database.scalars(select(Transaction).where(
            Transaction.merchant_id == merchant.id,
            Transaction.customer_reference.like(f"{OLD_SAMPLE_PREFIX}%"),
        )).all())
        all_transactions = list(database.scalars(select(Transaction).where(Transaction.merchant_id == merchant.id)).all())
        if any(transaction not in old_sample_transactions for transaction in all_transactions):
            raise SystemExit("Real or untagged transactions exist. No records were changed to protect merchant data.")

        old_generated_campaign = database.scalar(select(Campaign.id).where(
            Campaign.merchant_id == merchant.id,
            Campaign.name.like(f"[{SAMPLE_PREFIX}-%"),
        ).limit(1))
        if old_generated_campaign:
            raise SystemExit("A previous synthetic campaign batch exists without its transaction marker; review data before continuing.")

        for transaction in old_sample_transactions:
            database.delete(transaction)
        old_generated_movements = list(database.scalars(select(InventoryMovement).where(
            InventoryMovement.merchant_id == merchant.id,
            InventoryMovement.reason.like("Sample month %"),
        )).all())
        for movement in old_generated_movements:
            database.delete(movement)
        database.flush()

        existing_products = list(database.scalars(select(Product).where(Product.merchant_id == merchant.id)).all())
        products_by_sku = {product.sku.strip().upper(): product for product in existing_products}
        weights: dict[UUID, float] = {}
        created_products: set[UUID] = set()

        for spec in PRODUCT_SPECS:
            product = products_by_sku.get(spec.sku.strip().upper())
            if product is None:
                cost_multiplier = rng.uniform(spec.cost_ratio, min(spec.cost_ratio + 0.11, 0.94))
                cost = (spec.price * Decimal(str(cost_multiplier))).quantize(Decimal("0.01"))
                product = Product(
                    id=_stable_uuid(merchant_namespace, f"product:{spec.sku}"),
                    merchant_id=merchant.id,
                    name=spec.name,
                    category=spec.category,
                    sku=spec.sku,
                    unit_price=spec.price,
                    cost_price=cost,
                    stock_quantity=0,
                    low_stock_threshold=spec.threshold,
                    created_at=datetime.combine(first_day, time(5), tzinfo=IST),
                )
                database.add(product)
                database.flush()
                products_by_sku[spec.sku.strip().upper()] = product
                created_products.add(product.id)
            weights[product.id] = CATEGORY_WEIGHTS.get(product.category, 0.7) * spec.popularity

        for product in existing_products:
            weights.setdefault(product.id, CATEGORY_WEIGHTS.get(product.category, 0.7))

        products = list(products_by_sku.values())
        if not 100 <= len(products) <= 150:
            raise SystemExit(f"The existing catalog plus generated products totals {len(products)}; expected 100-150. No data committed.")

        sales = _build_sales(merchant, products, weights, first_day, days, transaction_count, batch_marker, rng, now_ist)
        units_sold: dict[UUID, int] = defaultdict(int)
        units_by_day: dict[date, dict[UUID, int]] = defaultdict(lambda: defaultdict(int))
        for sale in sales:
            sale_day = sale.created_at.astimezone(IST).date()
            for line in sale.lines:
                units_sold[line.product.id] += line.quantity
                units_by_day[sale_day][line.product.id] += line.quantity

        opening_stock: dict[UUID, int] = {}
        movement_history: dict[UUID, list[InventoryMovement]] = {}
        for product in products:
            history = list(database.scalars(select(InventoryMovement).where(
                InventoryMovement.merchant_id == merchant.id,
                InventoryMovement.product_id == product.id,
            )).all())
            starting_quantity = product.stock_quantity
            if product.id in created_products:
                starting_quantity = max(product.low_stock_threshold * 2, int(units_sold[product.id] * 0.08) + rng.randint(4, 14))
                product.stock_quantity = starting_quantity
            if history and sum(movement.quantity for movement in history) != starting_quantity:
                raise SystemExit(f"Existing movements do not reconcile for {product.name}; no data committed.")
            if not history:
                opening = InventoryMovement(
                    id=_stable_uuid(merchant_namespace, f"{batch_marker}:opening:{product.sku}"),
                    merchant_id=merchant.id,
                    product_id=product.id,
                    product_name=product.name,
                    movement_type="opening",
                    quantity=starting_quantity,
                    reason=f"SYNTHETIC {batch_marker} opening stock",
                    created_at=datetime.combine(first_day, time(5), tzinfo=IST),
                )
                database.add(opening)
                history.append(opening)
            opening_stock[product.id] = starting_quantity
            movement_history[product.id] = history

        sale_movements: dict[tuple[int, int], InventoryMovement] = {}
        for sale in sales:
            total = sum((sale_line.unit_price * sale_line.quantity for sale_line in sale.lines), start=Decimal("0.00")).quantize(Decimal("0.01"))
            transaction_id = _stable_uuid(merchant_namespace, f"{batch_marker}:transaction:{sale.sequence}")
            transaction = Transaction(
                id=transaction_id,
                merchant_id=merchant.id,
                total=total,
                payment_method=sale.payment_method,
                customer_reference=sale.customer_reference,
                created_at=sale.created_at,
            )
            for line_index, line in enumerate(sale.lines, start=1):
                line_total = (line.unit_price * line.quantity).quantize(Decimal("0.01"))
                transaction.items.append(TransactionItem(
                    id=_stable_uuid(merchant_namespace, f"{batch_marker}:item:{sale.sequence}:{line_index}"),
                    transaction_id=transaction_id,
                    product_id=line.product.id,
                    product_name=line.product.name,
                    sku=line.product.sku,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    line_total=line_total,
                ))
                movement_id = _stable_uuid(merchant_namespace, f"{batch_marker}:sale-movement:{sale.sequence}:{line_index}")
                sale_movements[(sale.sequence, line_index)] = InventoryMovement(
                    id=movement_id,
                    merchant_id=merchant.id,
                    product_id=line.product.id,
                    product_name=line.product.name,
                    movement_type="sale",
                    quantity=-line.quantity,
                    reason=f"SYNTHETIC {batch_marker} sale {transaction_id}",
                    created_at=sale.created_at,
                )
            database.add(transaction)

        movement_by_product: dict[UUID, list[InventoryMovement]] = defaultdict(list)
        for sale in sales:
            for line_index, line in enumerate(sale.lines, start=1):
                movement_by_product[line.product.id].append(sale_movements[(sale.sequence, line_index)])

        restock_count = 0
        adjustment_count = 0
        final_stock: dict[UUID, int] = {}
        weeks = [list(range(start, min(start + 7, days))) for start in range(0, days, 7)]
        for product in products:
            stock = opening_stock[product.id]
            for week_index, offsets in enumerate(weeks):
                week_first_day = first_day + timedelta(days=offsets[0])
                week_demand = sum(units_by_day[week_first_day + timedelta(days=offset - offsets[0])].get(product.id, 0) for offset in offsets)
                if week_index == len(weeks) - 1:
                    outcome = rng.random()
                    if outcome < 0.035:
                        target_closing = 0
                    elif outcome < 0.25:
                        target_closing = rng.randint(1, max(1, product.low_stock_threshold))
                    else:
                        target_closing = product.low_stock_threshold + rng.randint(3, 20)
                else:
                    target_closing = max(product.low_stock_threshold + rng.randint(3, 14), int(week_demand * 0.12))
                received = max(0, week_demand + target_closing - stock)
                if received:
                    restock_time = datetime.combine(week_first_day, time(5, 30), tzinfo=IST)
                    restock = InventoryMovement(
                        id=_stable_uuid(merchant_namespace, f"{batch_marker}:restock:{product.sku}:{week_index}"),
                        merchant_id=merchant.id,
                        product_id=product.id,
                        product_name=product.name,
                        movement_type="restock",
                        quantity=received,
                        reason=f"SYNTHETIC {batch_marker} supplier delivery week {week_index + 1}",
                        created_at=restock_time,
                    )
                    database.add(restock)
                    movement_by_product[product.id].append(restock)
                    restock_count += 1
                stock += received - week_demand
                if stock < 0:
                    raise RuntimeError(f"Inventory plan oversold {product.name} in week {week_index + 1}.")
                if week_index == len(weeks) - 1 and stock > target_closing:
                    adjustment = target_closing - stock
                    perishable = product.category in {"Dairy & bakery", "Fresh produce", "Frozen & ready-to-eat"}
                    movement_by_product[product.id].append(InventoryMovement(
                        id=_stable_uuid(merchant_namespace, f"{batch_marker}:adjustment:{product.sku}"),
                        merchant_id=merchant.id,
                        product_id=product.id,
                        product_name=product.name,
                        movement_type="adjustment",
                        quantity=adjustment,
                        reason=f"SYNTHETIC {batch_marker} {'expiry/wastage' if perishable else 'damaged-pack/count'} adjustment",
                        created_at=datetime.combine(today, time(22, 30), tzinfo=IST),
                    ))
                    stock = target_closing
                    adjustment_count += 1
            product.stock_quantity = stock
            final_stock[product.id] = stock
            ledger_stock = sum(movement.quantity for movement in movement_history[product.id])
            ledger_stock += sum(movement.quantity for movement in movement_by_product[product.id])
            if ledger_stock != stock:
                raise RuntimeError(f"Inventory reconciliation failed for {product.name}: ledger {ledger_stock}, product {stock}.")

        for movement_list in movement_by_product.values():
            database.add_all(movement_list)

        campaign_specs = [
            ("Weekend produce & pantry saver - SAMPLE", "In-store offer", "active", "Estimated 260 shoppers", 21),
            ("Staples value week - SAMPLE", "Paytm offer example", "expired", "Estimated 410 shoppers", 4),
            ("Dairy breakfast combo - SAMPLE", "In-store offer", "expired", "Estimated 180 shoppers", 10),
            ("Month-end household essentials - SAMPLE", "Paytm offer example", "scheduled", "Estimated 220 shoppers", 30),
        ]
        for index, (name, channel, status, reach, offset) in enumerate(campaign_specs, start=1):
            full_name = f"[{batch_marker}] {name}"
            database.add(Campaign(
                id=_stable_uuid(merchant_namespace, f"{batch_marker}:campaign:{index}"),
                merchant_id=merchant.id,
                name=full_name,
                channel=channel,
                status=status,
                reach=f"SYNTHETIC - {reach}",
                starts_at=datetime.combine(first_day + timedelta(days=offset), time(9), tzinfo=IST),
                created_at=datetime.combine(first_day, time(6), tzinfo=IST),
            ))

        database.flush()
        total_revenue = sum((sale_line.unit_price * sale_line.quantity for sale in sales for sale_line in sale.lines), start=Decimal("0.00"))
        category_counts: dict[str, int] = defaultdict(int)
        for product in products:
            category_counts[product.category] += 1
        print(f"Merchant: {merchant.business_name} ({merchant.id})")
        print(f"Synthetic batch: {batch_marker}; date range: {first_day} through {today}.")
        print(f"Products: {len(products)} across {len(category_counts)} categories.")
        print(f"Customers: 180 tagged customer references; transactions: {len(sales)}; transaction items: {sum(len(sale.lines) for sale in sales)}.")
        movement_total = sum(len(movement_by_product[product.id]) + len(movement_history[product.id]) for product in products)
        low_stock = sum(0 < final_stock[product.id] <= product.low_stock_threshold for product in products)
        out_of_stock = sum(final_stock[product.id] == 0 for product in products)
        print(f"Inventory movements: {movement_total}; restocks: {restock_count}; adjustments: {adjustment_count}; campaigns: {len(campaign_specs)}.")
        print(f"Closing stock alerts: {low_stock} low-stock, {out_of_stock} out-of-stock.")
        print(f"Total sample sales: ₹{total_revenue:,.2f}.")
        print("Product distribution: " + ", ".join(f"{category}={count}" for category, count in sorted(category_counts.items())))
        print("Closing stock was reconciled to the movement ledger for every product.")
        if dry_run:
            database.rollback()
            print("Dry run complete; all database changes were rolled back.")
            return
        database.commit()
    except Exception:
        database.rollback()
        raise
    finally:
        database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merchant", default="Balaji Super Market", help="Exact existing merchant business name")
    parser.add_argument("--days", type=int, default=30, help="Historical period in days (must be 30)")
    parser.add_argument("--transactions", type=int, default=TARGET_TRANSACTIONS, help="Synthetic transaction count (800-1500)")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report the dataset, then roll back all database writes")
    args = parser.parse_args()
    _seed(args.merchant, args.days, args.transactions, args.dry_run)


if __name__ == "__main__":
    main()
