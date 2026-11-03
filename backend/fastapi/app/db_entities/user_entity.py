
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    """사용자 기본 정보"""

    __tablename__ = "user"

    user_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )

    user_type: Mapped[str | None] = mapped_column(Text)
    origin_type: Mapped[str | None] = mapped_column(Text)
    user_status: Mapped[str | None] = mapped_column(Text)

    age_band: Mapped[str | None] = mapped_column(Text)
    district_code: Mapped[str | None] = mapped_column(Text)
    spend_band: Mapped[str | None] = mapped_column(Text)

    card_ownership_combo: Mapped[str | None] = mapped_column(Text)

    estimated_monthly_spend_won: Mapped[int | None] = mapped_column(
        Integer
    )

    dongbaek_usage_level: Mapped[str | None] = mapped_column(Text)
    seed_id: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )


class Account(Base):
    """사용자 연결 계좌"""

    __tablename__ = "account"

    account_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )

    user_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("user.user_id"),
        nullable=False,
    )

    account_role: Mapped[str | None] = mapped_column(Text)
    account_status: Mapped[str | None] = mapped_column(Text)

    opening_balance_won: Mapped[int | None] = mapped_column(
        Integer
    )

    opening_balance_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )

    origin_type: Mapped[str | None] = mapped_column(Text)


class DbWallet(Base):
    """동백전 지갑 및 잔액"""

    __tablename__ = "db_wallet"

    wallet_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )

    user_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("user.user_id"),
        nullable=False,
    )

    charge_won: Mapped[int | None] = mapped_column(Integer)
    cashback_won: Mapped[int | None] = mapped_column(Integer)
    policy_support_won: Mapped[int | None] = mapped_column(Integer)

    opening_balance_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )

    wallet_status: Mapped[str | None] = mapped_column(Text)
    origin_type: Mapped[str | None] = mapped_column(Text)


class Onecard(Base):
    """동백원패스 원카드 정보"""

    __tablename__ = "onecard"

    onecard_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )

    user_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("user.user_id"),
        nullable=False,
    )

    default_mode: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)

    issued_at: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date)

    replaces_onecard_id: Mapped[str | None] = mapped_column(Text)

    active_from: Mapped[date | None] = mapped_column(Date)
    active_to: Mapped[date | None] = mapped_column(Date)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )