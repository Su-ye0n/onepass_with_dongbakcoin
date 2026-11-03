
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db_entities.user_entity import (
    User,
    Account,
    DbWallet,
    Onecard,
)


class UserRepository:
    """사용자, 계좌, 동백전 지갑, 원카드 데이터 접근 계층"""

    def __init__(self, db: Session):
        self.db = db

    def get_user_by_id(
        self,
        user_id: str,
    ) -> User | None:
        """사용자 ID로 단건 조회"""

        statement = select(User).where(
            User.user_id == user_id
        )

        return self.db.scalar(statement)

    def get_users(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[User]:
        """사용자 목록 페이지 단위 조회"""

        statement = (
            select(User)
            .order_by(User.user_id)
            .offset(offset)
            .limit(limit)
        )

        return list(self.db.scalars(statement).all())

    def get_accounts_by_user_id(
        self,
        user_id: str,
    ) -> list[Account]:
        """사용자 연결 계좌 목록 조회"""

        statement = (
            select(Account)
            .where(Account.user_id == user_id)
            .order_by(Account.account_id)
        )

        return list(self.db.scalars(statement).all())

    def get_account_by_id(
        self,
        account_id: str,
    ) -> Account | None:
        """계좌 ID로 단건 조회"""

        statement = select(Account).where(
            Account.account_id == account_id
        )

        return self.db.scalar(statement)

    def get_wallets_by_user_id(
        self,
        user_id: str,
    ) -> list[DbWallet]:
        """사용자의 동백전 지갑 목록 조회"""

        statement = (
            select(DbWallet)
            .where(DbWallet.user_id == user_id)
            .order_by(DbWallet.wallet_id)
        )

        return list(self.db.scalars(statement).all())

    def get_wallet_by_id(
        self,
        wallet_id: str,
    ) -> DbWallet | None:
        """지갑 ID로 단건 조회"""

        statement = select(DbWallet).where(
            DbWallet.wallet_id == wallet_id
        )

        return self.db.scalar(statement)

    def get_onecards_by_user_id(
        self,
        user_id: str,
    ) -> list[Onecard]:
        """사용자 원카드 목록 조회"""

        statement = (
            select(Onecard)
            .where(Onecard.user_id == user_id)
            .order_by(Onecard.onecard_id)
        )

        return list(self.db.scalars(statement).all())

    def get_onecard_by_id(
        self,
        onecard_id: str,
    ) -> Onecard | None:
        """원카드 ID로 단건 조회"""

        statement = select(Onecard).where(
            Onecard.onecard_id == onecard_id
        )

        return self.db.scalar(statement)
