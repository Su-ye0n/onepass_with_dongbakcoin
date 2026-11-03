from fastapi import APIRouter

from app.api.v1.routers.health_router import router as health_router
from app.api.v1.routers.card_router import (
    router as card_router,
    user_card_router,
)
from app.api.v1.routers.benefit_router import router as benefit_router
from app.api.v1.routers.merchant_router import router as merchant_router
from app.api.v1.routers.payment_router import router as payment_router
from app.api.v1.routers.payment_router import (
    router as payment_router,
    user_payment_router,
)

from app.api.v1.routers.category_priority_router import (
    router as category_priority_router,
)


api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(card_router)
api_router.include_router(user_card_router)
api_router.include_router(benefit_router)
api_router.include_router(merchant_router)
api_router.include_router(payment_router)
api_router.include_router(user_payment_router)

# 업종별 카드 우선순위 API
api_router.include_router(category_priority_router)