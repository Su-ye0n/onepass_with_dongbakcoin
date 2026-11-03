
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db_entities.card_entity import (
    CardProduct,
    UserCard,
    CardMonthClose,
    CardPerfMonthClose,
)


class CardRepository:
    """카드 관련 데이터 접근 계층"""

    def __init__(self, db: Session):
        self.db = db

    def get_product_by_id(
        self,
        product_id: str,
    ) -> CardProduct | None:
        """카드 상품 ID로 조회"""

        statement = select(CardProduct).where(
            CardProduct.product_id == product_id
        )

        return self.db.scalar(statement)

    def get_all_products(self) -> list[CardProduct]:
        """전체 카드 상품 조회"""

        statement = select(CardProduct).order_by(
            CardProduct.product_id
        )

        return list(self.db.scalars(statement).all())

    def get_user_card_by_id(
        self,
        user_card_id: str,
    ) -> UserCard | None:
        """사용자 카드 ID로 조회"""

        statement = select(UserCard).where(
            UserCard.user_card_id == user_card_id
        )

        return self.db.scalar(statement)


    # 특정 사용자의 활성 카드 조회 (삭제된 카드가 목록에 나오지않게)
    def get_user_cards(
        self,
        user_id: str,
    ) -> list[UserCard]:
        """특정 사용자의 활성 카드 조회"""

        statement = (
            select(UserCard)
            .where(
                UserCard.user_id == user_id,
                UserCard.card_status == "ACTIVE"
            )
            .order_by(UserCard.user_card_id)
        )
        return list(self.db.scalars(statement).all())



    def get_month_close(
        self,
        user_card_id: str,
        base_month: str,
    ) -> CardMonthClose | None:
        """카드의 월별 이용 실적 조회"""

        statement = select(CardMonthClose).where(
            CardMonthClose.user_card_id == user_card_id,
            CardMonthClose.base_month == base_month,
        )

        return self.db.scalar(statement)

    def get_perf_month_close(
        self,
        user_card_id: str,
        base_month: str,
    ) -> list[CardPerfMonthClose]:
        """카드의 혜택 규칙별 월별 인정 실적 조회"""

        statement = (
            select(CardPerfMonthClose)
            .where(
                CardPerfMonthClose.user_card_id == user_card_id,
                CardPerfMonthClose.base_month == base_month,
            )
            .order_by(CardPerfMonthClose.rule_id)
        )

        return list(self.db.scalars(statement).all())




    # --------- 사용자 카드 삭제 ------------
    def deactivate_user_card(
        self,
        user_card: UserCard,
    ) -> UserCard:
        """등록된 사용자 카드 삭제"""

        user_card.card_status = "INACTIVE"

        self.db.add(user_card)
        self.db.commit()
        self.db.refresh(user_card)

        return user_card




    # --------- 사용자 카드 등록 ------------
    def create_user_card(
        self,
        user_card: UserCard,
    ) -> UserCard:
        """사용자 보유 카드 DB 저장"""

        self.db.add(user_card)
        self.db.commit()
        self.db.refresh(user_card)

        return user_card




    # --------- 사용자 카드 우선순위 설정 ------------
    def update_card_priorities(
        self,
        cards: list[UserCard],
        priorities: dict[str, int],
    ) -> list[UserCard]:
        """사용자 카드 우선순위를 한 번에 저장"""

        for card in cards:
            card.default_preference_rank = priorities[card.user_card_id]

        self.db.commit()

        for card in cards:
            self.db.refresh(card)

        return cards