
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db_entities.benefit_entity import (
    BenefitRule,
    BenefitIndustry,
    BenefitCapTier,
    CardPerfExclude,
)


class BenefitRepository:
    """카드 혜택 관련 데이터 접근 계층"""

    def __init__(self, db: Session):
        self.db = db

    def get_rule_by_id(
        self,
        rule_id: str,
    ) -> BenefitRule | None:
        """혜택 규칙 ID로 조회"""

        statement = select(BenefitRule).where(
            BenefitRule.rule_id == rule_id
        )

        return self.db.scalar(statement)

    def get_rules_by_product_id(
        self,
        product_id: str,
    ) -> list[BenefitRule]:
        """카드 상품별 혜택 규칙 조회"""

        statement = (
            select(BenefitRule)
            .where(BenefitRule.product_id == product_id)
            .order_by(BenefitRule.rule_id)
        )

        return list(self.db.scalars(statement).all())

    def get_industries_by_rule_id(
        self,
        rule_id: str,
    ) -> list[BenefitIndustry]:
        """혜택 규칙의 적용 및 제외 대상 조회"""

        statement = (
            select(BenefitIndustry)
            .where(BenefitIndustry.rule_id == rule_id)
            .order_by(
                BenefitIndustry.target_type,
                BenefitIndustry.target_code,
            )
        )

        return list(self.db.scalars(statement).all())

    def get_cap_tiers_by_product_id(
        self,
        product_id: str,
    ) -> list[BenefitCapTier]:
        """카드 상품별 실적 구간 혜택 한도 조회"""

        statement = (
            select(BenefitCapTier)
            .where(BenefitCapTier.product_id == product_id)
            .order_by(
                BenefitCapTier.perf_min_won,
                BenefitCapTier.tier_id,
            )
        )

        return list(self.db.scalars(statement).all())

    def get_perf_excludes_by_product_id(
        self,
        product_id: str,
    ) -> list[CardPerfExclude]:
        """카드 상품별 실적 제외 조건 조회"""

        statement = (
            select(CardPerfExclude)
            .where(CardPerfExclude.product_id == product_id)
            .order_by(CardPerfExclude.exclude_id)
        )

        return list(self.db.scalars(statement).all())

    def get_perf_excludes_by_rule_id(
        self,
        rule_id: str,
    ) -> list[CardPerfExclude]:
        """혜택 규칙별 실적 제외 조건 조회"""

        statement = (
            select(CardPerfExclude)
            .where(CardPerfExclude.rule_id == rule_id)
            .order_by(CardPerfExclude.exclude_id)
        )

        return list(self.db.scalars(statement).all())
