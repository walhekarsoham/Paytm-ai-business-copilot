from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai_copilot.analytics import build_merchant_context
from app.ai_copilot.chat import chat_with_copilot
from app.ai_copilot.schemas import AnalyzeRequest, ChatRequest, ChatResponse, CopilotAnalysis, MerchantBusinessContext, RecommendationResponse
from app.ai_copilot.service import analyze_business, recommend_actions
from app.api.dependencies import get_current_merchant, get_db
from app.models import Merchant

router = APIRouter(prefix="/ai-copilot", tags=["AI Copilot"])


@router.get("/context", response_model=MerchantBusinessContext)
def get_business_context(
    database: Session = Depends(get_db),
    merchant: Merchant = Depends(get_current_merchant),
) -> MerchantBusinessContext:
    return build_merchant_context(database, merchant)


@router.post("/analyze", response_model=CopilotAnalysis)
def analyze_merchant(
    payload: AnalyzeRequest,
    database: Session = Depends(get_db),
    merchant: Merchant = Depends(get_current_merchant),
) -> CopilotAnalysis:
    _, analysis = analyze_business(database, merchant, payload.question)
    return analysis


@router.get("/recommendations", response_model=RecommendationResponse)
def get_recommendations(
    database: Session = Depends(get_db),
    merchant: Merchant = Depends(get_current_merchant),
) -> RecommendationResponse:
    return recommend_actions(database, merchant)


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    database: Session = Depends(get_db),
    merchant: Merchant = Depends(get_current_merchant),
) -> ChatResponse:
    return chat_with_copilot(database, merchant, payload.message)
