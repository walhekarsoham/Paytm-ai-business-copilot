from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.ai_copilot.routes import router as ai_copilot_router
from app.api.routes import auth, campaigns, dashboard, inventory, products, transactions
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Authenticated merchant, sales, product, inventory, dashboard, and campaign APIs.",
    docs_url="/docs",
    redoc_url="/redoc",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(IntegrityError)
async def handle_integrity_error(_: Request, error: IntegrityError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": "The request conflicts with existing merchant data."})


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(products.router, prefix="/api/v1")
app.include_router(transactions.router, prefix="/api/v1")
app.include_router(inventory.router, prefix="/api/v1")
app.include_router(campaigns.router, prefix="/api/v1")
app.include_router(ai_copilot_router, prefix="/api/v1")
app.include_router(ai_copilot_router, prefix="/api")
