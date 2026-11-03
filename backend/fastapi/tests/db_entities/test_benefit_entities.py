from sqlalchemy import select

from app.core.database import SessionLocal
from app.db_entities.card_entity import CardProduct
from app.db_entities.benefit_entity import (
    BenefitRule,
    BenefitIndustry,
    BenefitCapTier,
    CardPerfExclude,
)


def test_benefit_entities_query():
    entities = [
        BenefitRule,
        BenefitIndustry,
        BenefitCapTier,
        CardPerfExclude,
    ]

    with SessionLocal() as db:
        for entity in entities:
            result = db.execute(
                select(entity).limit(5)
            )

            rows = result.scalars().all()

            print(
                f"{entity.__tablename__}: "
                f"{len(rows)}건 조회"
            )


if __name__ == "__main__":
    test_benefit_entities_query()