from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.api.auth_dependencies import get_current_user
from app.api.v1.routers.payment_router import (
    router,
    get_payment_service,
)
from app.services.payment_service import (
    PaymentService,
    RecommendationEngineNotAvailable,
)
from datetime import datetime
from app.api.v1.routers.payment_router import get_mock_payment_service

from app.services.payment_service import (
    PaymentService,
    RecommendationEngineNotAvailable,
    PaymentNotFoundError,
)
from app.services.payment_service import (
    PaymentService,
    RecommendationEngineNotAvailable,
    PaymentNotFoundError,
    PaymentValidationError,
)
from app.services.payment_service import (
    PaymentService,
    RecommendationEngineNotAvailable,
    PaymentNotFoundError,
    PaymentValidationError,
    DuplicatePaymentError,
)
from app.schemas.payment_schema import PaymentHistoryResponse

from app.api.v1.routers.payment_router import (
    router,
    user_payment_router,
    get_payment_service,
    get_mock_payment_service,
)





class FakePaymentService:
    """테스트용 결제 추천 서비스"""

    def recommend(self, request):
        return {
            "user_id": request.user_id,
            "merchant_id": request.merchant_id,
            "amount_won": request.amount_won,
            "recommended_user_card_id": "USER_CARD_001",
            "expected_benefit_won": 1500,
            "candidates": [
                {
                    "user_card_id": "USER_CARD_001",
                    "product_id": "CARD_001",
                    "product_name": "테스트 카드",
                    "expected_benefit_won": 1500,
                    "eligible": True,
                    "reason": "테스트용 추천 결과",
                }
            ],
        }


def create_test_client(service=None, mock_service=None, user_id="USER_001"):
    """테스트용 FastAPI 앱 생성"""

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.include_router(user_payment_router, prefix="/api/v1")

    if service is not None:
        app.dependency_overrides[get_payment_service] = (
            lambda: service
        )

    if mock_service is not None:
        app.dependency_overrides[get_mock_payment_service] = (
            lambda: mock_service
        )

    app.dependency_overrides[get_current_user] = (
        lambda: SimpleNamespace(user_id=user_id)
    )

    return TestClient(app)


# ========================================
# 1. 추천 엔진 미연결
# ========================================

def test_recommend_payment_engine_unavailable():
    with create_test_client(
        service=PaymentService(engine=None)
    ) as client:
        response = client.post(
            "/api/v1/payments/recommend",
            json={
                "user_id": "USER_001",
                "merchant_id": "MERCHANT_001",
                "amount_won": 30000,
            },
        )
    assert response.status_code == 503
    assert response.json()["detail"] == "추천 엔진이 아직 연결되지 않았습니다."


# ========================================
# 2. 규칙 엔진 연결
# ========================================

def test_recommend_payment_uses_rule_engine(monkeypatch):
    from app.adapters.rule_engine_adapter import RuleEngineAdapter

    called = {}

    def fake_recommend(self, user_id, merchant_id, amount_won):
        called["user_id"] = user_id
        called["merchant_id"] = merchant_id
        called["amount_won"] = amount_won

        return {
            "user_id": user_id,
            "merchant_id": merchant_id,
            "amount_won": amount_won,
            "recommended_user_card_id": "USER_CARD_001",
            "expected_benefit_won": 1500,
            "candidates": [
                {
                    "user_card_id": "USER_CARD_001",
                    "product_id": "CARD_001",
                    "product_name": "테스트 카드",
                    "expected_benefit_won": 1500,
                    "eligible": True,
                    "reason": "TEST",
                }
            ],
        }

    monkeypatch.setattr(
        RuleEngineAdapter,
        "recommend",
        fake_recommend,
    )

    # 의존성 재정의 없이 실제 API 라우터 호출
    with create_test_client() as client:
        response = client.post(
            "/api/v1/payments/recommend",
            json={
                "user_id": "USER_001",
                "merchant_id": "MERCHANT_001",
                "amount_won": 30000,
            },
        )

    assert response.status_code == 200
    assert called == {
        "user_id": "USER_001",
        "merchant_id": "MERCHANT_001",
        "amount_won": 30000,
    }

    data = response.json()
    assert data["recommended_user_card_id"] == "USER_CARD_001"
    assert data["expected_benefit_won"] == 1500


# ========================================
# 3. 잘못된 결제금액
# ========================================

def test_recommend_payment_invalid_amount():
    with create_test_client(FakePaymentService()) as client:
        response = client.post(
            "/api/v1/payments/recommend",
            json={
                "user_id": "USER_001",
                "merchant_id": "MERCHANT_001",
                "amount_won": -1000,
            },
        )

    assert response.status_code == 422


# ========================================
# 4. 필수 입력값 누락
# ========================================

def test_recommend_payment_missing_user_id():
    with create_test_client(FakePaymentService()) as client:
        response = client.post(
            "/api/v1/payments/recommend",
            json={
                "merchant_id": "MERCHANT_001",
                "amount_won": 30000,
            },
        )

    assert response.status_code == 422


# ========================================
# 5. 빈 사용자 ID
# ========================================

def test_recommend_payment_empty_user_id():
    with create_test_client(FakePaymentService()) as client:
        response = client.post(
            "/api/v1/payments/recommend",
            json={
                "user_id": "",
                "merchant_id": "MERCHANT_001",
                "amount_won": 30000,
            },
        )

    assert response.status_code == 422




# ========================================
# 6. 모의 결제 API 성공 테스트
# ========================================

def test_create_mock_payment_success():
    """모의 결제 API 성공 응답 테스트"""

    class FakeMockPaymentService:
        def create_mock_payment(self, request):
            return {
                "tx_id": "tx-test-001",
                "user_id": request.user_id,
                "user_card_id": request.user_card_id,
                "merchant_id": request.merchant_id,
                "amount_won": request.amount_won,
                "approval_status": "APPROVED",
                "event_at": datetime(2026, 10, 27, 10, 0),
            }

    with create_test_client(
        mock_service=FakeMockPaymentService(),
        user_id="user-001",
    ) as client:
        response = client.post(
            "/api/v1/payments",
            json={
                "request_id": "req-test-001",
                "user_id": "user-001",
                "user_card_id": "card-001",
                "merchant_id": "merchant-001",
                "amount_won": 10000,
            },
        )

    assert response.status_code == 201

    data = response.json()

    assert data["tx_id"] == "tx-test-001"
    assert data["user_id"] == "user-001"
    assert data["user_card_id"] == "card-001"
    assert data["merchant_id"] == "merchant-001"
    assert data["amount_won"] == 10000
    assert data["approval_status"] == "APPROVED"




# ========================================
# 7. 존재하지 않는 카드로 결제 요청
# ========================================

def test_create_mock_payment_card_not_found():
    """존재하지 않는 카드로 결제 시 404 반환"""

    class FakeMockPaymentService:
        def create_mock_payment(self, request):
            raise PaymentNotFoundError(
                "등록된 카드를 찾을 수 없습니다."
            )

    with create_test_client(
        mock_service=FakeMockPaymentService(),
        user_id="user-001",
    ) as client:
        response = client.post(
            "/api/v1/payments",
            json={
                "request_id": "req-test-002",
                "user_id": "user-001",
                "user_card_id": "nonexistent-card",
                "merchant_id": "merchant-001",
                "amount_won": 10000,
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "등록된 카드를 찾을 수 없습니다."
    )




# ========================================
# 8. 다른 사용자의 카드로 결제 요청
# ========================================

def test_create_mock_payment_card_owner_mismatch():
    """다른 사용자의 카드로 결제 시 403 반환"""

    class FakeMockPaymentService:
        def create_mock_payment(self, request):
            raise PaymentValidationError(
                "해당 사용자의 카드가 아닙니다."
            )

    with create_test_client(
        mock_service=FakeMockPaymentService()
    ) as client:
        response = client.post(
            "/api/v1/payments",
            json={
                "request_id": "req-test-003",
                "user_id": "USER_001",
                "user_card_id": "USER_CARD_999",
                "merchant_id": "MERCHANT_001",
                "amount_won": 10000,
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "해당 사용자의 카드가 아닙니다."
    )



# ========================================
# 9. 중복 결제 요청
# ========================================

def test_create_mock_payment_duplicate_request():
    """중복 결제 요청 시 409 반환"""

    class FakeMockPaymentService:
        def create_mock_payment(self, request):
            raise DuplicatePaymentError(
                "이미 처리된 결제 요청입니다."
            )

    with create_test_client(
        mock_service=FakeMockPaymentService()
    ) as client:
        response = client.post(
            "/api/v1/payments",
            json={
                "request_id": "req-test-001",
                "user_id": "USER_001",
                "user_card_id": "USER_CARD_001",
                "merchant_id": "MERCHANT_001",
                "amount_won": 10000,
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "이미 처리된 결제 요청입니다."
    )



# ========================================
# 10. 결제 상세 조회 성공
# ========================================

def test_get_payment_detail_success():
    """결제 상세 조회 성공 시 200 반환"""

    class FakeMockPaymentService:
        def get_payment_detail(self, tx_id):
            return {
                "tx_id": tx_id,
                "user_id": "USER_001",
                "user_card_id": "USER_CARD_001",
                "merchant_id": "MERCHANT_001",
                "amount_won": 10000,
                "approval_status": "APPROVED",
                "event_at": datetime(2026, 10, 27, 10, 0),
            }

    with create_test_client(
        mock_service=FakeMockPaymentService()
    ) as client:
        response = client.get(
            "/api/v1/payments/tx-test-001"
        )

    assert response.status_code == 200

    data = response.json()

    assert data["tx_id"] == "tx-test-001"
    assert data["user_id"] == "USER_001"
    assert data["amount_won"] == 10000
    assert data["approval_status"] == "APPROVED"




# ========================================
# 11. 존재하지 않는 결제 내역 조회
# ========================================

def test_get_payment_detail_not_found():
    """존재하지 않는 tx_id 조회 시 404 반환"""

    class FakeMockPaymentService:
        def get_payment_detail(self, tx_id):
            raise PaymentNotFoundError(
                "결제 내역을 찾을 수 없습니다."
            )

    with create_test_client(
        mock_service=FakeMockPaymentService(),
        user_id="USER_999",
    ) as client:
        response = client.get(
            "/api/v1/payments/nonexistent-tx"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "결제 내역을 찾을 수 없습니다."
    )




# ========================================
# 12. 사용자별 결제 내역 조회 성공
# ========================================

def test_get_payment_history_success():
    """사용자별 결제 내역 조회 시 200 반환"""

    class FakeMockPaymentService:
        def get_payment_history(self, user_id):
            return {
                "payments": [
                    {
                        "tx_id": "tx-test-001",
                        "user_id": user_id,
                        "user_card_id": "USER_CARD_001",
                        "merchant_id": "MERCHANT_001",
                        "amount_won": 10000,
                        "approval_status": "APPROVED",
                        "event_at": datetime(2026, 10, 27, 10, 0),
                    }
                ]
            }

    with create_test_client(
        mock_service=FakeMockPaymentService()
    ) as client:
        response = client.get(
            "/api/v1/users/USER_001/payments"
        )

    assert response.status_code == 200

    data = response.json()

    assert len(data["payments"]) == 1
    assert data["payments"][0]["tx_id"] == "tx-test-001"
    assert data["payments"][0]["user_id"] == "USER_001"
    assert data["payments"][0]["amount_won"] == 10000




# ========================================
# 13. 결제 내역이 없는 사용자
# ========================================

def test_get_payment_history_empty():
    """결제 내역이 없으면 빈 목록 반환"""

    class FakeMockPaymentService:
        def get_payment_history(self, user_id):
            return {"payments": []}

    with create_test_client(
        mock_service=FakeMockPaymentService(),
        user_id="USER_999",
    ) as client:
        response = client.get(
            "/api/v1/users/USER_999/payments"
        )

    assert response.status_code == 200
    assert response.json() == {"payments": []}









# ========================================
# 14. 거래 이력 확장 필드 검증
# ========================================

from types import SimpleNamespace
from unittest.mock import Mock


def test_payment_detail_extended_fields():
    """거래 이력에 가맹점명, 카드명, 혜택 금액 등이 포함되는지 검증"""

    service = PaymentService()

    # 실제 DB 대신 Repository 응답을 모의 처리
    service.merchant_repo = Mock()
    service.card_repo = Mock()

    service.merchant_repo.get_merchant_by_id.return_value = (
        SimpleNamespace(merchant_name="테스트 카페")
    )

    service.card_repo.get_user_card_by_id.return_value = (
        SimpleNamespace(product_id="PRODUCT_001")
    )

    service.card_repo.get_product_by_id.return_value = (
        SimpleNamespace(product_name="동백전")
    )

    ledger = SimpleNamespace(
        tx_id="TX_001",
        user_id="USER_001",
        user_card_id="USER_CARD_001",
        merchant_id="MERCHANT_001",
        gross_purchase_won=15000,
        approval_status="APPROVED",
        event_at=datetime(2026, 10, 27, 10, 0),
        awarded_benefit_won=500,
        source_mode="MOCK",
        event_note="모의 결제 승인",
    )

    result = service._build_payment_detail(ledger)

    assert result.tx_id == "TX_001"
    assert result.merchant_name == "테스트 카페"
    assert result.product_name == "동백전"
    assert result.awarded_benefit_won == 500
    assert result.source_mode == "MOCK"
    assert result.event_note == "모의 결제 승인"

    service.merchant_repo.get_merchant_by_id.assert_called_once_with(
        "MERCHANT_001"
    )
    service.card_repo.get_product_by_id.assert_called_once_with(
        "PRODUCT_001"
    )