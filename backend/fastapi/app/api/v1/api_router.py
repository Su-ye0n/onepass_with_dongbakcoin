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

from app.api.v1.routers.admin_router import router as admin_router
from app.api.v1.routers.category_priority_router import (
    router as category_priority_router,
)
from app.api.v1.routers.auth_router import router as auth_router
from app.api.v1.routers.identity_card_router import (
    router as identity_card_router,
)
from app.api.v1.routers.user_router import router as user_router


api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(identity_card_router)
api_router.include_router(card_router)
api_router.include_router(user_card_router)
api_router.include_router(benefit_router)
api_router.include_router(merchant_router)
api_router.include_router(payment_router)
api_router.include_router(user_payment_router)
api_router.include_router(user_router)

# 업종별 카드 우선순위 API
api_router.include_router(category_priority_router)

# 직원 대시보드 API (읽기 전용)
api_router.include_router(admin_router)
