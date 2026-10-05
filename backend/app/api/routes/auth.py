from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_merchant, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models import Merchant
from app.schemas import AuthResponse, MerchantCreate, MerchantLogin, MerchantRead

router = APIRouter(prefix="/auth", tags=["authentication"])


def auth_response(merchant: Merchant) -> AuthResponse:
    return AuthResponse(access_token=create_access_token(merchant.id), merchant=MerchantRead.model_validate(merchant))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: MerchantCreate, database: Session = Depends(get_db)) -> AuthResponse:
    merchant = Merchant(
        business_name=payload.business_name.strip(),
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
    )
    database.add(merchant)
    try:
        database.commit()
        database.refresh(merchant)
    except IntegrityError:
        database.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.") from None
    return auth_response(merchant)


@router.post("/login", response_model=AuthResponse)
def login(payload: MerchantLogin, database: Session = Depends(get_db)) -> AuthResponse:
    merchant = database.scalar(select(Merchant).where(Merchant.email == str(payload.email).lower()))
    if merchant is None or not verify_password(payload.password, merchant.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth_response(merchant)


@router.get("/me", response_model=MerchantRead)
def current_merchant(merchant: Merchant = Depends(get_current_merchant)) -> Merchant:
    return merchant