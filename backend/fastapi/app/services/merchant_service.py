from app.db_entities.merchant_entity import Merchant
from app.repositories.merchant_repository import MerchantRepository




# --------- 가맹점 조회 ------------
class MerchantService:
    """가맹점 관련 비즈니스 로직"""

    def __init__(self, repository: MerchantRepository):
        self.repository = repository

    # --------- 가맹점 목록 조회 ------------
    def get_merchants(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Merchant]:
        """가맹점 목록 페이지 단위 조회"""

        return self.repository.get_all_merchants(
            limit=limit,
            offset=offset,
        )

    # --------- 가맹점 단건 조회 ------------
    def get_merchant(
        self,
        merchant_id: str,
    ) -> Merchant | None:
        """가맹점 ID로 단건 조회"""

        return self.repository.get_merchant_by_id(merchant_id)