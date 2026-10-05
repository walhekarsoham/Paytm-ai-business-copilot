from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InventoryMovement, Product, Transaction, TransactionItem
from app.schemas import TransactionCreate


def record_transaction(database: Session, merchant_id: UUID, payload: TransactionCreate) -> Transaction:
    requested: dict[UUID, int] = defaultdict(int)
    for item in payload.items:
        requested[item.product_id] += item.quantity

    try:
        products = database.scalars(
            select(Product)
            .where(Product.merchant_id == merchant_id, Product.id.in_(requested))
            .order_by(Product.id)
            .with_for_update()
        ).all()
        products_by_id = {product.id: product for product in products}
        if len(products_by_id) != len(requested):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more products were not found.")
        for product_id, quantity in requested.items():
            product = products_by_id[product_id]
            if product.stock_quantity < quantity:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Insufficient stock for {product.name}. Available: {product.stock_quantity}.",
                )

        total = sum(
            (products_by_id[item.product_id].unit_price * item.quantity for item in payload.items),
            start=Decimal("0.00"),
        ).quantize(Decimal("0.01"))
        transaction = Transaction(
            merchant_id=merchant_id,
            total=total,
            payment_method=payload.payment_method,
            customer_reference=payload.customer_reference,
        )
        database.add(transaction)
        database.flush()

        for item in payload.items:
            product = products_by_id[item.product_id]
            line_total = (product.unit_price * item.quantity).quantize(Decimal("0.01"))
            transaction.items.append(TransactionItem(
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                quantity=item.quantity,
                unit_price=product.unit_price,
                line_total=line_total,
            ))
        for product_id, quantity in requested.items():
            product = products_by_id[product_id]
            product.stock_quantity -= quantity
            database.add(InventoryMovement(
                merchant_id=merchant_id,
                product_id=product.id,
                product_name=product.name,
                movement_type="sale",
                quantity=-quantity,
                reason=f"Sale {transaction.id}",
            ))
        database.commit()
        database.refresh(transaction)
        return transaction
    except HTTPException:
        database.rollback()
        raise
    except Exception:
        database.rollback()
        raise