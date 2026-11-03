from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db_entities.ledger_entity import Ledger
from app.db_entities.user_entity import DbWallet, User, UserProfile
from app.schemas.user_schema import (
    UserProfileResponse,
    UserProfileUpdateRequest,
    WalletAccountResponse,
    WalletBalanceResponse,
    WalletTopUpRequest,
    WalletTopUpResponse,
)


class UserNotFoundError(Exception):
    """사용자를 찾을 수 없음"""


class WalletNotFoundError(Exception):
    """활성 지갑을 찾을 수 없음"""


class WalletSelectionError(Exception):
    """사용할 지갑 선택이 모호함"""


class DuplicateTopUpError(Exception):
    """요청 ID가 다른 충전 요청에서 이미 사용됨"""


class UserService:
    def __init__(self, db: Session):
        self.db = db

    def get_profile(self, user_id: str) -> UserProfileResponse:
        user = self._get_user(user_id)
        profile = self.db.get(UserProfile, user_id)
        return UserProfileResponse(
            user_id=user.user_id,
            display_name=profile.display_name if profile else None,
            student_card_id=profile.student_card_id if profile else None,
            university=profile.university if profile else None,
            department=profile.department if profile else None,
            phone_number=profile.phone_number if profile else None,
            address=profile.address if profile else None,
            source_mode=(
                profile.source_mode
                if profile and profile.source_mode
                else user.origin_type or "UNKNOWN"
            ),
        )

    def update_profile(
        self,
        user_id: str,
        request: UserProfileUpdateRequest,
    ) -> UserProfileResponse:
        user = self._get_user(user_id)
        profile = self.db.get(UserProfile, user_id)
        now = datetime.now()
        if profile is None:
            profile = UserProfile(
                user_id=user_id,
                source_mode=user.origin_type or "UNKNOWN",
                created_at=now,
            )
            self.db.add(profile)

        profile.display_name = request.display_name
        profile.student_card_id = request.student_card_id
        profile.university = request.university
        profile.department = request.department
        profile.phone_number = request.phone_number
        profile.address = request.address
        profile.updated_at = now
        self.db.commit()
        self.db.refresh(user)
        self.db.refresh(profile)
        return self.get_profile(user_id)

    def get_wallet_balance(self, user_id: str) -> WalletBalanceResponse:
        self._get_user(user_id)
        wallets = self._get_active_wallets(user_id)
        if not wallets:
            raise WalletNotFoundError("사용자의 활성 지갑을 찾을 수 없습니다.")
        wallet_responses = [self._wallet_response(wallet) for wallet in wallets]
        return WalletBalanceResponse(
            user_id=user_id,
            balance_won=sum(wallet.balance_won for wallet in wallet_responses),
            wallets=wallet_responses,
        )

    def top_up(
        self,
        user_id: str,
        request: WalletTopUpRequest,
    ) -> WalletTopUpResponse:
        self._get_user(user_id)
        wallets = self._get_active_wallets(user_id, lock=True)
        if request.wallet_id:
            wallet = next(
                (item for item in wallets if item.wallet_id == request.wallet_id),
                None,
            )
            if wallet is None:
                raise WalletNotFoundError("사용자의 활성 지갑을 찾을 수 없습니다.")
        elif len(wallets) == 1:
            wallet = wallets[0]
        elif not wallets:
            raise WalletNotFoundError("사용자의 활성 지갑을 찾을 수 없습니다.")
        else:
            raise WalletSelectionError("충전할 지갑을 지정해 주세요.")

        existing = self.db.scalar(
            select(Ledger).where(
                Ledger.request_id == request.request_id,
                Ledger.event_type == "TOPUP",
            )
        )
        if existing is not None:
            return self._replay_top_up(existing, user_id, wallet, request)

        amount = request.amount_won
        wallet.charge_won = (wallet.charge_won or 0) + amount
        now = datetime.now()
        ledger = Ledger(
            tx_id=str(uuid4()),
            request_id=request.request_id,
            user_id=user_id,
            wallet_id=wallet.wallet_id,
            event_at=now,
            event_seq=1,
            event_type="TOPUP",
            bucket_type="DB_CHARGE",
            delta_won=amount,
            approval_status="APPROVED",
            source_mode="MOCK",
            event_note="Synthetic demo top-up; no real payment was processed.",
        )
        self.db.add(ledger)

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.db.scalar(
                select(Ledger).where(
                    Ledger.request_id == request.request_id,
                    Ledger.event_type == "TOPUP",
                )
            )
            if existing is None:
                raise
            return self._replay_top_up(existing, user_id, wallet, request)

        self.db.refresh(wallet)
        self.db.refresh(ledger)
        return self._top_up_response(ledger, user_id, wallet, amount)

    def _get_user(self, user_id: str) -> User:
        user = self.db.get(User, user_id)
        if user is None:
            raise UserNotFoundError("사용자를 찾을 수 없습니다.")
        return user

    def _get_active_wallets(
        self,
        user_id: str,
        lock: bool = False,
    ) -> list[DbWallet]:
        statement = (
            select(DbWallet)
            .where(
                DbWallet.user_id == user_id,
                DbWallet.wallet_status == "ACTIVE",
            )
            .order_by(DbWallet.wallet_id)
        )
        if lock:
            statement = statement.with_for_update()
        return list(self.db.scalars(statement).all())

    @staticmethod
    def _wallet_response(wallet: DbWallet) -> WalletAccountResponse:
        charge = wallet.charge_won or 0
        cashback = wallet.cashback_won or 0
        support = wallet.policy_support_won or 0
        return WalletAccountResponse(
            wallet_id=wallet.wallet_id,
            charge_won=charge,
            cashback_won=cashback,
            policy_support_won=support,
            balance_won=charge + cashback + support,
        )

    def _replay_top_up(
        self,
        existing: Ledger,
        user_id: str,
        wallet: DbWallet,
        request: WalletTopUpRequest,
    ) -> WalletTopUpResponse:
        if (
            existing.user_id != user_id
            or existing.wallet_id != wallet.wallet_id
            or existing.delta_won != request.amount_won
        ):
            raise DuplicateTopUpError(
                "이미 다른 충전 요청에 사용된 request_id입니다."
            )
        self.db.refresh(wallet)
        return self._top_up_response(
            existing,
            user_id,
            wallet,
            request.amount_won,
        )

    def _top_up_response(
        self,
        ledger: Ledger,
        user_id: str,
        wallet: DbWallet,
        amount_won: int,
    ) -> WalletTopUpResponse:
        wallet_response = self._wallet_response(wallet)
        return WalletTopUpResponse(
            tx_id=ledger.tx_id or "",
            request_id=ledger.request_id or "",
            user_id=user_id,
            wallet_id=wallet.wallet_id,
            amount_won=amount_won,
            balance_won=wallet_response.balance_won,
            charge_won=wallet_response.charge_won,
            cashback_won=wallet_response.cashback_won,
            policy_support_won=wallet_response.policy_support_won,
            approval_status="APPROVED",
            source_mode="MOCK",
            event_at=ledger.event_at or datetime.now(),
        )
