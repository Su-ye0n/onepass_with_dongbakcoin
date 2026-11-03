
from sqlalchemy import select

from app.core.database import SessionLocal
from app.db_entities.category_entity import (
    BenefitCategoryMap,
    UserCategory,
    UserCategoryPriority,
)


def test_category_entities_query():
    entities = [
        BenefitCategoryMap,
        UserCategory,
        UserCategoryPriority,
    ]

    with SessionLocal() as db:
        for entity in entities:
            statement = select(entity).limit(5)

            result = db.execute(statement)
            rows = result.scalars().all()

            print(
                f"{entity.__tablename__}: "
                f"{len(rows)}건 조회"
            )


if __name__ == "__main__":
    test_category_entities_query()