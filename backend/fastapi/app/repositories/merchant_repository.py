
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db_entities.merchant_entity import Merchant


class MerchantRepository:
    """가맹점 관련 데이터 접근 계층"""

    def __init__(self, db: Session):
        self.db = db

    def get_merchant_by_id(
        self,
        merchant_id: str,
    ) -> Merchant | None:
        """가맹점 ID로 단건 조회"""

        statement = select(Merchant).where(
            Merchant.merchant_id == merchant_id
        )

        return self.db.scalar(statement)

    def get_all_merchants(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Merchant]:
        """전체 가맹점 페이지 단위 조회"""

        statement = (
            select(Merchant)
            .order_by(Merchant.merchant_id)
            .offset(offset)
            .limit(limit)
        )

        return list(self.db.scalars(statement).all())

    def get_merchants_by_industry_code(
        self,
        industry_code: str,
    ) -> list[Merchant]:
        """업종 코드별 가맹점 조회"""

        statement = (
            select(Merchant)
            .where(Merchant.industry_code == industry_code)
            .order_by(Merchant.merchant_id)
        )

        return list(self.db.scalars(statement).all())

    def get_merchants_by_sales_band(
        self,
        sales_band: str,
    ) -> list[Merchant]:
        """매출 구간별 가맹점 조회"""

        statement = (
            select(Merchant)
            .where(Merchant.sales_band == sales_band)
            .order_by(Merchant.merchant_id)
        )

        return list(self.db.scalars(statement).all())

    def get_merchants_by_region_code(
        self,
        region_code: str,
    ) -> list[Merchant]:
        """지역 코드별 가맹점 조회"""

        statement = (
            select(Merchant)
            .where(Merchant.region_code == region_code)
            .order_by(Merchant.merchant_id)
        )

        return list(self.db.scalars(statement).all())

    def get_merchants_by_dongbaek_status(
        self,
        dongbaek_status: str,
    ) -> list[Merchant]:
        """동백전 가맹 상태별 조회"""

        statement = (
            select(Merchant)
            .where(Merchant.dongbaek_status == dongbaek_status)
            .order_by(Merchant.merchant_id)
        )

        return list(self.db.scalars(statement).all())

    def get_qr_merchants(self) -> list[Merchant]:
        """QR 결제 지원 가맹점 조회"""

        statement = (
            select(Merchant)
            .where(Merchant.is_qr_merchant == 1)
            .order_by(Merchant.merchant_id)
        )

        return list(self.db.scalars(statement).all())

    def get_dbplus_merchants(self) -> list[Merchant]:
        """동백플러스 가맹점 조회"""

        statement = (
            select(Merchant)
            .where(Merchant.is_dbplus_shop == 1)
            .order_by(Merchant.merchant_id)
        )

        return list(self.db.scalars(statement).all())