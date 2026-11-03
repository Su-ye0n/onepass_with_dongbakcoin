from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db_entities.card_entity import CardProduct, UserCard
from app.db_entities.merchant_entity import Merchant
from app.db_entities.policy_entity import DbPolicy, DbPolicyRate
from app.db_entities.user_entity import DbWallet, Onecard, User


class AdminRepository:
    """직원 대시보드용 조회 (읽기 전용)"""

    def __init__(self, db: Session):
        self.db = db

    # --------- 사용자 ------------
    def get_users(self) -> list[User]:
        statement = select(User).order_by(User.user_id)
        return list(self.db.scalars(statement).all())

    def get_wallet_status_by_user(self) -> dict[str, str | None]:
        """사용자별 동백전 지갑 상태. 지갑 행이 없으면 키가 없음"""

        statement = select(DbWallet.user_id, DbWallet.wallet_status)
        result: dict[str, str | None] = {}

        for user_id, status in self.db.execute(statement):
            # 한 사용자에 지갑이 여러 개면 ACTIVE를 우선
            if result.get(user_id) != "ACTIVE":
                result[user_id] = status

        return result

    def get_user_cards_with_product(self) -> list[tuple[UserCard, CardProduct | None]]:
        statement = (
            select(UserCard, CardProduct)
            .outerjoin(
                CardProduct,
                CardProduct.product_id == UserCard.product_id,
            )
            .order_by(UserCard.user_id, UserCard.default_preference_rank)
        )
        return [(row[0], row[1]) for row in self.db.execute(statement)]

    def count_active_onecards(self) -> int:
        statement = select(func.count()).select_from(Onecard).where(
            Onecard.status == "ACTIVE"
        )
        return int(self.db.scalar(statement) or 0)

    # --------- 카드 상품 ------------
    def get_card_products(self) -> list[CardProduct]:
        return list(self.db.scalars(select(CardProduct)).all())

    # --------- 가맹점 ------------
    def count_merchants_by_industry_status(self) -> list[tuple[str, str | None, int]]:
        statement = select(
            Merchant.industry_code,
            Merchant.dongbaek_status,
            func.count(),
        ).group_by(Merchant.industry_code, Merchant.dongbaek_status)
        return [(r[0], r[1], int(r[2])) for r in self.db.execute(statement)]

    def count_merchants_by_sales_band(self) -> list[tuple[str | None, int]]:
        statement = select(Merchant.sales_band, func.count()).group_by(
            Merchant.sales_band
        )
        return [(r[0], int(r[1])) for r in self.db.execute(statement)]

    def get_merchants_by_ids(self, merchant_ids: list[str]) -> list[Merchant]:
        if not merchant_ids:
            return []
        statement = select(Merchant).where(
            Merchant.merchant_id.in_(merchant_ids)
        )
        return list(self.db.scalars(statement).all())

    # --------- 동백전 정책 ------------
    def get_policies_with_rates(self) -> list[tuple[DbPolicy, list[DbPolicyRate]]]:
        policies = list(
            self.db.scalars(select(DbPolicy).order_by(DbPolicy.valid_from)).all()
        )
        rates = list(self.db.scalars(select(DbPolicyRate)).all())

        by_policy: dict[str, list[DbPolicyRate]] = {}
        for rate in rates:
            by_policy.setdefault(rate.policy_id, []).append(rate)

        return [(p, by_policy.get(p.policy_id, [])) for p in policies]
