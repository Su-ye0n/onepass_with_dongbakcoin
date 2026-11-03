from fastapi import APIRouter, Depends, HTTPException

from app.schemas.payment_schema import (
    PaymentRecommendRequest,
    PaymentRecommendResponse,
)
from app.services.payment_service import (
    PaymentService,
    RecommendationEngineNotAvailable,
)



from sqlalchemy.orm import Session

from app.api.dependencies import get_db

from app.schemas.payment_schema import (
    MockPaymentRequest,
    MockPaymentResponse,
)

from app.services.payment_service import (
    PaymentValidationError,
    PaymentNotFoundError,
    DuplicatePaymentError,
)
from app.schemas.payment_schema import PaymentDetailResponse
from app.schemas.payment_schema import PaymentHistoryResponse
from app.adapters.rule_engine_adapter import RuleEngineAdapter
from app.api.auth_dependencies import get_current_user, require_path_user
from app.db_entities.user_entity import User






# --------- 최적 결제수단 추천 API ------------
router = APIRouter(
    prefix="/payments",
    tags=["Payments"],
)


# ---------- 최적 결제수단 추천 서비스 생성함수 --------
def get_payment_service() -> PaymentService:
    """추천 Service 의존성 주입"""
    return PaymentService(
        engine=RuleEngineAdapter(),
    )

    # 팀원 추천 엔진 연결 전에는 None 사용
    return PaymentService(engine=None)


# -----------모의 결제 서비스 생성함수 --------
def get_mock_payment_service(
    db: Session = Depends(get_db),
) -> PaymentService:
    """모의 결제 서비스 의존성 주입"""

    return PaymentService(db=db)




# --------- 최적 결제수단 추천 ------------
@router.post(
    "/recommend",
    response_model=PaymentRecommendResponse,
)
def recommend_payment(
    request: PaymentRecommendRequest,
    service: PaymentService = Depends(get_payment_service),
    current_user: User = Depends(get_current_user),
):
    """최적 결제수단 추천 요청"""

    if request.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="본인 계정만 사용할 수 있습니다.")
    try:
        return service.recommend(request)

    except RecommendationEngineNotAvailable as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc



# --------- 모의 결제 처리 ------------
@router.post(
    "",
    response_model=MockPaymentResponse,
    status_code=201,
)
def create_mock_payment(
    request: MockPaymentRequest,
    service: PaymentService = Depends(get_mock_payment_service),
    current_user: User = Depends(get_current_user),
):
    """모의 결제 실행"""

    if request.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="본인 계정만 사용할 수 있습니다.")
    try:
        return service.create_mock_payment(request)

    except PaymentNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except PaymentValidationError as exc:
        raise HTTPException(
            status_code=403,
            detail=str(exc),
        ) from exc

    except DuplicatePaymentError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc




# --------- 결제 상세 조회 ------------
@router.get(
    "/{tx_id}",
    response_model=PaymentDetailResponse,
)
def get_payment_detail(
    tx_id: str,
    service: PaymentService = Depends(get_mock_payment_service),
    current_user: User = Depends(get_current_user),
):
    """결제 상세 조회"""

    try:
        payment = service.get_payment_detail(tx_id)
        payment_user_id = (
            payment["user_id"] if isinstance(payment, dict) else payment.user_id
        )
        if payment_user_id != current_user.user_id:
            raise HTTPException(status_code=404, detail="결제 내역을 찾을 수 없습니다.")
        return payment

    except PaymentNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc




# 사용자별 결제내역조회
user_payment_router = APIRouter(
    prefix="/users",
    tags=["payments"],
    dependencies=[Depends(require_path_user)],
)


@user_payment_router.get(
    "/{user_id}/payments",
    response_model=PaymentHistoryResponse,
)
def get_payment_history(
    user_id: str,
    service: PaymentService = Depends(get_mock_payment_service),
):
    """사용자별 결제 내역 조회"""

    return service.get_payment_history(user_id)