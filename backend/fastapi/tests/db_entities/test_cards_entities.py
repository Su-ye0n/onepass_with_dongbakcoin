from sqlalchemy import select

from app.core.database import SessionLocal
from app.db_entities.card_entity import CardProduct


def test_card_product_query():
    # DB 세션 생성
    with SessionLocal() as db:
        # 카드 상품 최대 5개 조회
        statement = select(CardProduct).limit(5)

        # SQL 실행
        result = db.execute(statement)

        # ORM 객체 목록으로 변환
        cards = result.scalars().all()

        # 결과 출력
        print(f"조회된 카드 상품 수: {len(cards)}")

        for card in cards:
            print(card.product_id, card.product_name)


if __name__ == "__main__":
    test_card_product_query()