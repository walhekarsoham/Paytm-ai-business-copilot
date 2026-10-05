from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_merchant, get_db
from app.models import InventoryMovement, Merchant, Product
from app.schemas import InventoryMovementRead, InventoryRead, ProductRead, StockCount, StockRestock, ThresholdUpdate
from app.services.inventory import get_owned_product, movement_for_product, update_stock

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("", response_model=InventoryRead)
def read_inventory(
    database: Session = Depends(get_db),
    merchant: Merchant = Depends(get_current_merchant),
) -> InventoryRead:
    products = database.scalars(
        select(Product).where(Product.merchant_id == merchant.id).order_by(Product.name)
    ).all()
    movements = database.scalars(
        select(InventoryMovement)
        .where(InventoryMovement.merchant_id == merchant.id)
        .order_by(InventoryMovement.created_at.desc())
        .limit(10_000)
    ).all()
    return InventoryRead(
        products=[ProductRead.model_validate(product) for product in products],
        movements=[InventoryMovementRead.model_validate(movement) for movement in movements],
    )


@router.post("/products/{product_id}/restock", response_model=ProductRead)
def restock_product(
    product_id: UUID,
    payload: StockRestock,
    database: Session = Depends(get_db),
    merchant: Merchant = Depends(get_current_merchant),
) -> Product:
    return update_stock(database, merchant.id, product_id, payload.quantity, payload.reason, restock=True)


@router.post("/products/{product_id}/count", response_model=ProductRead)
def set_stock_count(
    product_id: UUID,
    payload: StockCount,
    database: Session = Depends(get_db),
    merchant: Merchant = Depends(get_current_merchant),
) -> Product:
    return update_stock(database, merchant.id, product_id, payload.stock_quantity, payload.reason, restock=False)


@router.patch("/products/{product_id}/threshold", response_model=ProductRead)
def set_low_stock_threshold(
    product_id: UUID,
    payload: ThresholdUpdate,
    database: Session = Depends(get_db),
    merchant: Merchant = Depends(get_current_merchant),
) -> Product:
    product = get_owned_product(database, merchant.id, product_id, lock=True)
    product.low_stock_threshold = payload.low_stock_threshold
    database.commit()
    database.refresh(product)
    return product