from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InventoryMovement, Product


def movement_for_product(merchant_id: UUID, product: Product, quantity: int, movement_type: str, reason: str) -> InventoryMovement:
    return InventoryMovement(
        merchant_id=merchant_id,
        product_id=product.id,
        product_name=product.name,
        movement_type=movement_type,
        quantity=quantity,
        reason=reason,
    )


def get_owned_product(database: Session, merchant_id: UUID, product_id: UUID, *, lock: bool = False) -> Product:
    statement = select(Product).where(Product.id == product_id, Product.merchant_id == merchant_id)
    if lock:
        statement = statement.with_for_update()
    product = database.scalar(statement)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    return product


def update_stock(
    database: Session,
    merchant_id: UUID,
    product_id: UUID,
    quantity: int,
    reason: str,
    *,
    restock: bool,
) -> Product:
    try:
        product = get_owned_product(database, merchant_id, product_id, lock=True)
        delta = quantity if restock else quantity - product.stock_quantity
        if delta == 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Stock is already at that quantity.")
        product.stock_quantity += delta
        database.add(InventoryMovement(
            merchant_id=merchant_id,
            product_id=product.id,
            product_name=product.name,
            movement_type="restock" if restock else "adjustment",
            quantity=delta,
            reason=reason.strip() or ("Supplier restock" if restock else "Physical stock count"),
        ))
        database.commit()
        database.refresh(product)
        return product
    except HTTPException:
        database.rollback()
        raise
    except Exception:
        database.rollback()
        raise