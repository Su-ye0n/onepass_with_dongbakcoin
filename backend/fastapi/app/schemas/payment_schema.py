from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime




#--------- 최적 결제수단 추천 (요청) -----------   -
class PaymentRecommendRequest(BaseModel):
    """최적 결제수단 추천 요청"""

    user_id: str = Field(min_length=1)
    merchant_id: str = Field(min_length=1)
    amount_won: int = Field(gt=0)


class PaymentMethodCandidate(BaseModel):
    """결제수단별 예상 혜택"""

    user_card_id: str
    product_id: str | None = None
    product_name: str | None = None

    expected_benefit_won: int = Field(ge=0)
    eligible: bool

    reason: str | None = None


#--------- 최적 결제수단 추천 (응답) ------------
class PaymentRecommendResponse(BaseModel):
    """최적 결제수단 추천 응답"""

    model_config = ConfigDict(from_attributes=True)

    user_id: str
    merchant_id: str
    amount_won: int

    recommended_user_card_id: str | None = None
    expected_benefit_won: int = Field(default=0, ge=0)

    candidates: list[PaymentMethodCandidate] = Field(
        default_factory=list
    )








#--------- 모의 결제 요청/응답 ------------
class MockPaymentRequest(BaseModel):
    """모의 결제 요청"""

    request_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    user_card_id: str = Field(min_length=1)
    merchant_id: str = Field(min_length=1)
    amount_won: int = Field(gt=0)


class MockPaymentResponse(BaseModel):
    """모의 결제 응답"""

    tx_id: str
    user_id: str
    user_card_id: str
    merchant_id: str

    amount_won: int
    approval_status: str
    event_at: datetime


class PaymentDetailResponse(BaseModel):
    """결제 상세 조회 응답"""

    tx_id: str
    user_id: str
    user_card_id: str
    merchant_id: str

    amount_won: int
    approval_status: str
    event_at: datetime

    # 거래 이력 화면에 필요한 추가 정보
    merchant_name: str | None = None
    product_name: str | None = None
    awarded_benefit_won: int | None = None
    source_mode: str | None = None
    event_note: str | None = None




class PaymentHistoryResponse(BaseModel):
    """사용자 결제 내역 응답"""

    payments: list[PaymentDetailResponse]


class PaymentCancelResponse(BaseModel):
    """모의 결제 취소 응답"""

    tx_id: str
    approval_status: str
    cancelled_at: datetime