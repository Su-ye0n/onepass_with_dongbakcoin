
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Identity, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Ledger(Base):
    """결제, 충전, 캐시백 등 거래 원장 이벤트"""

    __tablename__ = "ledger"

    # 기본 키
    ledger_id: Mapped[int] = mapped_column(
        Integer,
        Identity(),
        primary_key=True,
    )

    # 거래 식별 정보
    tx_id: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(Text)

    # 거래 관련 참조 정보
    user_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("user.user_id"),
    )

    user_card_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("user_card.user_card_id"),
    )

    account_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("account.account_id"),
    )

    wallet_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("db_wallet.wallet_id"),
    )

    merchant_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("merchant.merchant_id"),
    )

    # 거래 발생 시각 및 순서
    event_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )

    event_seq: Mapped[int | None] = mapped_column(Integer)

    # 거래 이벤트 유형
    event_type: Mapped[str | None] = mapped_column(Text)
    bucket_type: Mapped[str | None] = mapped_column(Text)

    # 거래 금액
    delta_won: Mapped[int | None] = mapped_column(Integer)
    gross_purchase_won: Mapped[int | None] = mapped_column(Integer)
    cashback_eligible_base_won: Mapped[int | None] = mapped_column(Integer)
    awarded_benefit_won: Mapped[int | None] = mapped_column(Integer)

    # 혜택 규칙 및 정책
    rule_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("benefit_rule.rule_id"),
    )

    policy_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("db_policy.policy_id"),
    )

    # 취소 또는 역거래 참조
    reverses_ledger_id: Mapped[int | None] = mapped_column(Integer)

    # 거래 상태 및 데이터 출처
    approval_status: Mapped[str | None] = mapped_column(Text)
    source_mode: Mapped[str | None] = mapped_column(Text)
    event_note: Mapped[str | None] = mapped_column(Text)