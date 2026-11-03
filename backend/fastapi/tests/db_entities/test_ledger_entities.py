
from sqlalchemy import select

from app.core.database import SessionLocal
from app.db_entities.ledger_entity import Ledger


def test_ledger_entity_query():
    with SessionLocal() as db:
        statement = select(Ledger).limit(5)

        result = db.execute(statement)
        rows = result.scalars().all()

        print(f"ledger: {len(rows)}건 조회")

        for row in rows:
            print(
                f"ledger_id={row.ledger_id}, "
                f"tx_id={row.tx_id}, "
                f"event_type={row.event_type}, "
                f"delta_won={row.delta_won}"
            )


if __name__ == "__main__":
    test_ledger_entity_query()