
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db_entities.ledger_entity import Ledger


class LedgerRepository:
    """결제 및 거래 원장 데이터 접근 계층"""

    def __init__(self, db: Session):
        self.db = db




    def get_ledger_by_id(
        self,
        ledger_id: int,
    ) -> Ledger | None:
        """원장 ID로 단건 조회"""

        statement = select(Ledger).where(
            Ledger.ledger_id == ledger_id
        )

        return self.db.scalar(statement)





    def get_ledgers_by_user_id(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Ledger]:
        """사용자별 거래 원장 조회"""

        statement = (
            select(Ledger)
            .where(Ledger.user_id == user_id)
            .order_by(
                Ledger.event_at.desc(),
                Ledger.event_seq.desc(),
                Ledger.ledger_id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        return list(self.db.scalars(statement).all())





    def get_ledgers_by_tx_id(
        self,
        tx_id: str,
    ) -> list[Ledger]:
        """거래 ID에 연결된 원장 목록 조회"""

        statement = (
            select(Ledger)
            .where(Ledger.tx_id == tx_id)
            .order_by(
                Ledger.event_seq,
                Ledger.ledger_id,
            )
        )

        return list(self.db.scalars(statement).all())




    def get_ledgers_by_request_id(
        self,
        request_id: str,
    ) -> list[Ledger]:
        """요청 ID에 연결된 원장 목록 조회"""

        statement = (
            select(Ledger)
            .where(Ledger.request_id == request_id)
            .order_by(
                Ledger.event_at,
                Ledger.event_seq,
                Ledger.ledger_id,
            )
        )

        return list(self.db.scalars(statement).all())




    def get_ledgers_by_user_card_id(
        self,
        user_card_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Ledger]:
        """사용자 카드별 거래 원장 조회"""

        statement = (
            select(Ledger)
            .where(Ledger.user_card_id == user_card_id)
            .order_by(
                Ledger.event_at.desc(),
                Ledger.event_seq.desc(),
                Ledger.ledger_id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        return list(self.db.scalars(statement).all())





    def get_ledgers_by_event_type(
        self,
        event_type: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Ledger]:
        """이벤트 유형별 거래 원장 조회"""

        statement = (
            select(Ledger)
            .where(Ledger.event_type == event_type)
            .order_by(
                Ledger.event_at.desc(),
                Ledger.event_seq.desc(),
                Ledger.ledger_id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        return list(self.db.scalars(statement).all())






    def get_ledgers_by_user_and_period(
        self,
        user_id: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[Ledger]:
        """사용자의 특정 기간 거래 원장 조회"""

        statement = (
            select(Ledger)
            .where(
                Ledger.user_id == user_id,
                Ledger.event_at >= start_at,
                Ledger.event_at < end_at,
            )
            .order_by(
                Ledger.event_at,
                Ledger.event_seq,
                Ledger.ledger_id,
            )
        )

        return list(self.db.scalars(statement).all())





    def get_ledgers_by_merchant_id(
        self,
        merchant_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Ledger]:
        """가맹점별 거래 원장 조회"""

        statement = (
            select(Ledger)
            .where(Ledger.merchant_id == merchant_id)
            .order_by(
                Ledger.event_at.desc(),
                Ledger.event_seq.desc(),
                Ledger.ledger_id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        return list(self.db.scalars(statement).all())



    # -- 거래 원장 이벤트를 DB 세션에 추가 ------
    def create_ledger(
        self,
        ledger: Ledger,
    ) -> Ledger:
        self.db.add(ledger)
        self.db.flush()

        return ledger