from fastapi import APIRouter

from app.api.v1.routers.card_router import (
    router as card_router,
    user_card_router,
)

api_router = APIRouter()

api_router.include_router(card_router)
api_router.include_router(user_card_router)