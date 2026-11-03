
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db_entities.policy_entity import (
    DbPolicy,
    DbPolicyRate,
    DbPolicyBonus,
)


class PolicyRepository:
    """동백전 정책 관련 데이터 접근 계층"""

    def __init__(self, db: Session):
        self.db = db

    def get_policy_by_id(
        self,
        policy_id: str,
    ) -> DbPolicy | None:
        """정책 ID로 조회"""

        statement = select(DbPolicy).where(
            DbPolicy.policy_id == policy_id
        )

        return self.db.scalar(statement)

    def get_all_policies(self) -> list[DbPolicy]:
        """전체 동백전 정책 조회"""

        statement = select(DbPolicy).order_by(
            DbPolicy.policy_id
        )

        return list(self.db.scalars(statement).all())

    def get_rates_by_policy_id(
        self,
        policy_id: str,
    ) -> list[DbPolicyRate]:
        """정책별 매출 구간 캐시백 비율 조회"""

        statement = (
            select(DbPolicyRate)
            .where(DbPolicyRate.policy_id == policy_id)
            .order_by(DbPolicyRate.sales_band)
        )

        return list(self.db.scalars(statement).all())

    def get_rate_by_sales_band(
        self,
        policy_id: str,
        sales_band: str,
    ) -> DbPolicyRate | None:
        """정책과 매출 구간에 해당하는 캐시백 비율 조회"""

        statement = select(DbPolicyRate).where(
            DbPolicyRate.policy_id == policy_id,
            DbPolicyRate.sales_band == sales_band,
        )

        return self.db.scalar(statement)

    def get_bonuses_by_policy_id(
        self,
        policy_id: str,
    ) -> list[DbPolicyBonus]:
        """정책별 추가 혜택 목록 조회"""

        statement = (
            select(DbPolicyBonus)
            .where(DbPolicyBonus.policy_id == policy_id)
            .order_by(DbPolicyBonus.bonus_id)
        )

        return list(self.db.scalars(statement).all())

    def get_bonus_by_id(
        self,
        bonus_id: int,
    ) -> DbPolicyBonus | None:
        """추가 혜택 ID로 조회"""

        statement = select(DbPolicyBonus).where(
            DbPolicyBonus.bonus_id == bonus_id
        )

        return self.db.scalar(statement)