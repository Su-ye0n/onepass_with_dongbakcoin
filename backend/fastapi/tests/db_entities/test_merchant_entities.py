
from sqlalchemy import select

from app.core.database import SessionLocal
from app.db_entities.merchant_entity import Merchant


def test_merchant_entity_query():
    with SessionLocal() as db:
        # 가맹점 최대 5개 조회
        statement = select(Merchant).limit(5)

        result = db.execute(statement)
        merchants = result.scalars().all()

        print(f"조회된 가맹점 수: {len(merchants)}")

        for merchant in merchants:
            print(
                f"가맹점 ID: {merchant.merchant_id}, "
                f"가맹점명: {merchant.merchant_name}, "
                f"업종 코드: {merchant.industry_code}"
            )


if __name__ == "__main__":
    test_merchant_entity_query()
