from typing import Any



from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db_entities.ledger_entity import Ledger
from app.repositories.card_repository import CardRepository
from app.repositories.merchant_repository import MerchantRepository
from app.repositories.ledger_repository import LedgerRepository

from app.schemas.payment_schema import (
    MockPaymentRequest,
    MockPaymentResponse,
    PaymentRecommendRequest,
    PaymentRecommendResponse,
    PaymentDetailResponse,
    PaymentHistoryResponse,
)



class RecommendationEngineNotAvailable(Exception):
    """추천 엔진이 아직 연결되지 않은 경우"""


class PaymentService:
    """최적 결제수단 추천 API와 추천 엔진 연결 계층"""


    # ---------- 생성자 ------------
    def __init__(self,
                 engine = None,
                 db : Session = None):
        self.engine = engine
        self.db = db

        # ---- 의미 : DB세션이 전달됬을때만 respository 객체를 생성하겠다 ----
        if db is not None:
            self.card_repo = CardRepository(db)
            self.merchant_repo = MerchantRepository(db)
            self.ledger_repo = LedgerRepository(db)



    # --------- 최적 결제수단 추천 ------------
    def recommend(
        self,
        request: PaymentRecommendRequest,
    ) -> PaymentRecommendResponse:
        """추천 엔진에 요청을 전달하고 결과를 반환"""

        if self.engine is None:
            raise RecommendationEngineNotAvailable(
                "추천 엔진이 아직 연결되지 않았습니다."
            )

        result = self.engine.recommend(
            user_id=request.user_id,
            merchant_id=request.merchant_id,
            amount_won=request.amount_won,
        )

        return PaymentRecommendResponse.model_validate(result)


    # --------- 모의 결제 처리 ------------
    def create_mock_payment(
        self,
        request: MockPaymentRequest,
    ) -> MockPaymentResponse:
        

        if self.db is None:
            raise RuntimeError("DB 세션이 연결되지 않았습니다.")

        # 1. 중복 결제 요청 확인
        existing = self.ledger_repo.get_ledgers_by_request_id(
            request.request_id
        )

        if existing:
            raise DuplicatePaymentError(
                "이미 처리된 결제 요청입니다."
            )

        # 2. 사용자 카드 확인
        user_card = self.card_repo.get_user_card_by_id(
            request.user_card_id
        )

        if user_card is None:
            raise PaymentNotFoundError(
                "등록된 카드를 찾을 수 없습니다."
            )

        # 3. 카드 소유자 확인
        if user_card.user_id != request.user_id:
            raise PaymentValidationError(
                "해당 사용자의 카드가 아닙니다."
            )

        # 4. 가맹점 확인
        merchant = self.merchant_repo.get_merchant_by_id(
            request.merchant_id
        )

        if merchant is None:
            raise PaymentNotFoundError(
                "가맹점을 찾을 수 없습니다."
            )

        # 5. 모의 결제 데이터 생성
        tx_id = str(uuid4())
        event_at = datetime.now()

        ledger = Ledger(
            tx_id=tx_id,
            request_id=request.request_id,
            user_id=request.user_id,
            user_card_id=request.user_card_id,
            merchant_id=request.merchant_id,
            event_at=event_at,
            event_seq=1,
            event_type="PAYMENT",
            gross_purchase_won=request.amount_won,
            delta_won=-request.amount_won,
            awarded_benefit_won=0,
            approval_status="APPROVED",
            source_mode="MOCK",
            event_note="모의 결제 승인",
        )

        # 6. 거래 원장 저장
        try:
            self.ledger_repo.create_ledger(ledger)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        # 7. 결제 결과 반환
        return MockPaymentResponse(
            tx_id=tx_id,
            user_id=request.user_id,
            user_card_id=request.user_card_id,
            merchant_id=request.merchant_id,
            amount_won=request.amount_won,
            approval_status="APPROVED",
            event_at=event_at,
        )







    # --------- 거래 이력 응답 생성 ------------
    def _build_payment_detail(
        self,
        ledger: Ledger,
    ) -> PaymentDetailResponse:
        """원장 데이터를 화면용 거래 이력 응답으로 변환"""

        # 가맹점 이름 조회
        merchant = None

        if ledger.merchant_id:
            merchant = self.merchant_repo.get_merchant_by_id(
                ledger.merchant_id
            )

        merchant_name = (
            merchant.merchant_name
            if merchant is not None
            else None
        )

        # 카드 상품 이름 조회
        product_name = None

        if ledger.user_card_id:
            user_card = self.card_repo.get_user_card_by_id(
                ledger.user_card_id
            )

            if user_card is not None and user_card.product_id:
                product = self.card_repo.get_product_by_id(
                    user_card.product_id
                )

                if product is not None:
                    product_name = product.product_name

        return PaymentDetailResponse(
            tx_id=ledger.tx_id,
            user_id=ledger.user_id,
            user_card_id=ledger.user_card_id,
            merchant_id=ledger.merchant_id,
            amount_won=ledger.gross_purchase_won,
            approval_status=ledger.approval_status,
            event_at=ledger.event_at,
            merchant_name=merchant_name,
            product_name=product_name,
            awarded_benefit_won=ledger.awarded_benefit_won,
            source_mode=ledger.source_mode,
            event_note=ledger.event_note,
        )















    # --------- 결제 상세 조회 ------------
    def get_payment_detail(self, tx_id: str):
        """거래 ID로 결제 상세 조회"""

        if self.db is None:
            raise RuntimeError("DB 세션이 연결되지 않았습니다.")

        ledgers = self.ledger_repo.get_ledgers_by_tx_id(tx_id)

        if not ledgers:
            raise PaymentNotFoundError(
                "결제 내역을 찾을 수 없습니다."
            )

        payment = next(
            (ledger for ledger in ledgers if ledger.event_type == "PAYMENT"),
            None,
        )

        if payment is None:
            raise PaymentNotFoundError(
                "결제 내역을 찾을 수 없습니다."
            )

        return self._build_payment_detail(payment)






    # --------- 사용자별 결제 내역조회 ------------
    def get_payment_history(
        self,
        user_id: str,
    ) -> PaymentHistoryResponse:
        """사용자별 모의 결제 내역 조회"""

        if self.db is None:
            raise RuntimeError("DB 세션이 연결되지 않았습니다.")

        ledgers = self.ledger_repo.get_ledgers_by_user_id(user_id)

        payments = []

        for ledger in ledgers:
            # 결제 승인 이벤트만 조회
            if ledger.event_type != "PAYMENT":
                continue

            payments.append(self._build_payment_detail(ledger))

        return PaymentHistoryResponse(payments=payments)



# --------- 결제 예외처리 ---------------
class PaymentValidationError(Exception):
    """결제 요청 검증 실패"""

class PaymentNotFoundError(Exception):
    """결제 대상 정보 없음"""

class DuplicatePaymentError(Exception):
    """중복 결제 요청"""