
from sqlalchemy import select

from app.core.database import SessionLocal
from app.db_entities.registration_entity import (
    CardVerifier,
    IssuedDemoCard,
    OwnedCard,
)


def test_registration_entities_query():
    entities = [
        CardVerifier,
        IssuedDemoCard,
        OwnedCard,
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
    test_registration_entities_query()