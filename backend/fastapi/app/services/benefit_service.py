from app.db_entities.benefit_entity import BenefitRule
from app.repositories.benefit_repository import BenefitRepository


# --------- 카드 혜택 조회 ------------
class BenefitService:
    """카드 혜택 조회 서비스"""

    def __init__(self, repository: BenefitRepository):
        self.repository = repository

    def get_rule_by_id(self, rule_id: str) -> BenefitRule | None:
        """혜택 규칙 ID로 단건 조회"""
        return self.repository.get_rule_by_id(rule_id)

    def get_rules_by_product_id(
        self,
        product_id: str,
    ) -> list[BenefitRule]:
        """카드 상품 ID로 혜택 규칙 목록 조회"""
        return self.repository.get_rules_by_product_id(product_id)