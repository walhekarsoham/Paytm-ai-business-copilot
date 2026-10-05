from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_merchant, get_db
from app.models import Merchant, Transaction
from app.schemas import TransactionCreate, TransactionRead
from app.services.sales import record_transaction

router = APIRouter(prefix="/transactions", tags=["sales"])


@router.get("", response_model=list[TransactionRead])
def list_transactions(
    today: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=1_000),
    database: Session = Depends(get_db),
    merchant: Merchant = Depends(get_current_merchant),
) -> list[Transaction]:
    filters = [Transaction.merchant_id == merchant.id]
    if today:
        merchant_timezone = ZoneInfo("Asia/Kolkata")
        today_local = datetime.now(merchant_timezone).date()
        today_start = datetime.combine(today_local, time.min, tzinfo=merchant_timezone).astimezone(timezone.utc)
        tomorrow_start = datetime.combine(today_local + timedelta(days=1), time.min, tzinfo=merchant_timezone).astimezone(timezone.utc)
        filters.extend((Transaction.created_at >= today_start, Transaction.created_at < tomorrow_start))
    return list(database.scalars(
        select(Transaction)
        .where(*filters)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    ).all())


@router.post("", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate,
    database: Session = Depends(get_db),
    merchant: Merchant = Depends(get_current_merchant),
) -> Transaction:
    return record_transaction(database, merchant.id, payload)