
from app.core.database import SessionLocal
from app.repositories.merchant_repository import MerchantRepository


def test_get_merchant_by_id_not_found():
    with SessionLocal() as db:
        repository = MerchantRepository(db)

        merchant = repository.get_merchant_by_id(
            "__nonexistent_test_merchant__"
        )

        assert merchant is None


def test_get_all_merchants():
    with SessionLocal() as db:
        repository = MerchantRepository(db)

        merchants = repository.get_all_merchants(
            limit=5,
            offset=0,
        )

        assert isinstance(merchants, list)
        assert len(merchants) <= 5

        print(f"조회된 가맹점 수: {len(merchants)}")


def test_get_merchants_by_industry_code():
    with SessionLocal() as db:
        repository = MerchantRepository(db)

        merchants = repository.get_merchants_by_industry_code(
            "__nonexistent_test_industry__"
        )

        assert merchants == []


def test_get_merchants_by_sales_band():
    with SessionLocal() as db:
        repository = MerchantRepository(db)

        merchants = repository.get_merchants_by_sales_band(
            "__nonexistent_test_band__"
        )

        assert merchants == []


def test_get_merchants_by_region_code():
    with SessionLocal() as db:
        repository = MerchantRepository(db)

        merchants = repository.get_merchants_by_region_code(
            "__nonexistent_test_region__"
        )

        assert merchants == []


def test_get_merchants_by_dongbaek_status():
    with SessionLocal() as db:
        repository = MerchantRepository(db)

        merchants = repository.get_merchants_by_dongbaek_status(
            "__nonexistent_test_status__"
        )

        assert merchants == []


def test_get_qr_merchants():
    with SessionLocal() as db:
        repository = MerchantRepository(db)

        merchants = repository.get_qr_merchants()

        assert isinstance(merchants, list)

        for merchant in merchants:
            assert merchant.is_qr_merchant == 1


def test_get_dbplus_merchants():
    with SessionLocal() as db:
        repository = MerchantRepository(db)

        merchants = repository.get_dbplus_merchants()

        assert isinstance(merchants, list)

        for merchant in merchants:
            assert merchant.is_dbplus_shop == 1