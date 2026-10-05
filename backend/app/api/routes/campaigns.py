from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_merchant, get_db
from app.models import Campaign, Merchant
from app.schemas import CampaignRead

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("", response_model=list[CampaignRead])
def list_campaigns(
    database: Session = Depends(get_db),
    merchant: Merchant = Depends(get_current_merchant),
) -> list[Campaign]:
    return list(database.scalars(
        select(Campaign).where(Campaign.merchant_id == merchant.id).order_by(Campaign.created_at.desc())
    ).all())