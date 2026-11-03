
from app.core.database import SessionLocal
from app.repositories.card_repository import CardRepository


def test_get_all_products():
    with SessionLocal() as db:
        repository = CardRepository(db)

        products = repository.get_all_products()

        assert isinstance(products, list)

        print(f"카드 상품 수: {len(products)}")

        for product in products[:5]:
            print(
                f"상품 ID: {product.product_id}, "
                f"상품명: {product.product_name}"
            )


def test_get_product_by_id_not_found():
    with SessionLocal() as db:
        repository = CardRepository(db)

        product = repository.get_product_by_id(
            "__nonexistent_test_product__"
        )

        assert product is None


def test_get_user_cards():
    with SessionLocal() as db:
        repository = CardRepository(db)

        cards = repository.get_user_cards(
            "__nonexistent_test_user__"
        )

        assert isinstance(cards, list)
        assert cards == []

        print(f"사용자 카드 수: {len(cards)}")
