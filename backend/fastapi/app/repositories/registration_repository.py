
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db_entities.registration_entity import (
    CardVerifier,
    IssuedDemoCard,
    OwnedCard,
)


class RegistrationRepository:
    """카드 검증, 데모 카드 발급 및 등록 정보 접근 계층"""

    def __init__(self, db: Session):
        self.db = db

    def get_verifier_by_issuance_id(
        self,
        issuance_id: str,
    ) -> CardVerifier | None:
        """발급 ID로 카드 검증 정보 조회"""

        statement = select(CardVerifier).where(
            CardVerifier.issuance_id == issuance_id
        )

        return self.db.scalar(statement)

    def get_verifiers_by_owner_id(
        self,
        owner_id: str,
    ) -> list[CardVerifier]:
        """소유자별 카드 검증 정보 조회"""

        statement = (
            select(CardVerifier)
            .where(CardVerifier.owner_id == owner_id)
            .order_by(CardVerifier.issuance_id)
        )

        return list(self.db.scalars(statement).all())

    def get_issued_card_by_id(
        self,
        issuance_id: str,
    ) -> IssuedDemoCard | None:
        """발급 ID로 데모 카드 조회"""

        statement = select(IssuedDemoCard).where(
            IssuedDemoCard.issuance_id == issuance_id
        )

        return self.db.scalar(statement)

    def get_issued_cards_by_owner_id(
        self,
        owner_id: str,
    ) -> list[IssuedDemoCard]:
        """소유자별 데모 카드 목록 조회"""

        statement = (
            select(IssuedDemoCard)
            .where(IssuedDemoCard.owner_id == owner_id)
            .order_by(IssuedDemoCard.issuance_id)
        )

        return list(self.db.scalars(statement).all())

    def get_owned_card_by_id(
        self,
        owned_card_id: str,
    ) -> OwnedCard | None:
        """등록 카드 ID로 단건 조회"""

        statement = select(OwnedCard).where(
            OwnedCard.owned_card_id == owned_card_id
        )

        return self.db.scalar(statement)

    def get_owned_cards_by_user_id(
        self,
        user_id: str,
    ) -> list[OwnedCard]:
        """사용자별 등록 카드 목록 조회"""

        statement = (
            select(OwnedCard)
            .where(OwnedCard.user_id == user_id)
            .order_by(OwnedCard.owned_card_id)
        )

        return list(self.db.scalars(statement).all())

    def get_owned_card_by_user_and_issuance(
        self,
        user_id: str,
        issuance_id: str,
    ) -> OwnedCard | None:
        """사용자와 발급 ID로 카드 등록 여부 조회"""

        statement = select(OwnedCard).where(
            OwnedCard.user_id == user_id,
            OwnedCard.issuance_id == issuance_id,
        )

        return self.db.scalar(statement)

    def get_owned_cards_by_product_id(
        self,
        product_id: str,
    ) -> list[OwnedCard]:
        """카드 상품별 등록 카드 목록 조회"""

        statement = (
            select(OwnedCard)
            .where(OwnedCard.product_id == product_id)
            .order_by(OwnedCard.owned_card_id)
        )

        return list(self.db.scalars(statement).all())
