from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_merchant, get_db
from app.models import Merchant, Product
from app.schemas import ProductCreate, ProductRead, ProductUpdate
from app.services.inventory import movement_for_product

router = APIRouter(prefix="/products", tags=["products"])


def get_product(database: Session, merchant_id: UUID, product_id: UUID) -> Product:
    product = database.scalar(select(Product).where(Product.id == product_id, Product.merchant_id == merchant_id))
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    return product


@router.get("", response_model=list[ProductRead])
def list_products(
    database: Session = Depends(get_db),
    merchant: Merchant = Depends(get_current_merchant),
) -> list[Product]:
    return list(database.scalars(
        select(Product).where(Product.merchant_id == merchant.id).order_by(Product.name)
    ).all())


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    database: Session = Depends(get_db),
    merchant: Merchant = Depends(get_current_merchant),
) -> Product:
    product = Product(merchant_id=merchant.id, **payload.model_dump())
    database.add(product)
    try:
        database.flush()
        if product.stock_quantity > 0:
            database.add(movement_for_product(merchant.id, product, product.stock_quantity, "opening", "Opening stock"))
        database.commit()
        database.refresh(product)
    except IntegrityError:
        database.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A product with this SKU already exists.") from None
    return product


@router.get("/{product_id}", response_model=ProductRead)
def read_product(
    product_id: UUID,
    database: Session = Depends(get_db),
    merchant: Merchant = Depends(get_current_merchant),
) -> Product:
    return get_product(database, merchant.id, product_id)


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    database: Session = Depends(get_db),
    merchant: Merchant = Depends(get_current_merchant),
) -> Product:
    product = get_product(database, merchant.id, product_id)
    previous_stock = product.stock_quantity
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in updates.items():
        setattr(product, field, value)
    try:
        if product.stock_quantity != previous_stock:
            database.add(movement_for_product(
                merchant.id,
                product,
                product.stock_quantity - previous_stock,
                "adjustment",
                "Stock updated while editing product",
            ))
        database.commit()
        database.refresh(product)
    except IntegrityError:
        database.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A product with this SKU already exists.") from None
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: UUID,
    database: Session = Depends(get_db),
    merchant: Merchant = Depends(get_current_merchant),
) -> None:
    product = get_product(database, merchant.id, product_id)
    database.delete(product)
    database.commit()