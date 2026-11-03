
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CardProduct(Base):
    """카드 상품 정보"""

    __tablename__ = "card_product"

    product_id: Mapped[str] = mapped_column(Text, primary_key=True)
    product_name: Mapped[str | None] = mapped_column(Text)
    issuer: Mapped[str | None] = mapped_column(Text)
    card_type: Mapped[str | None] = mapped_column(Text)
    product_status: Mapped[str | None] = mapped_column(Text)
    terms_version: Mapped[str | None] = mapped_column(Text)
    source_status: Mapped[str | None] = mapped_column(Text)
    source_ref: Mapped[str | None] = mapped_column(Text)


class UserCard(Base):
    """사용자가 보유한 카드"""

    __tablename__ = "user_card"

    user_card_id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("user.user_id")
    )
    product_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("card_product.product_id")
    )
    db_wallet_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("db_wallet.wallet_id")
    )
    linked_account_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("account.account_id")
    )
    card_status: Mapped[str | None] = mapped_column(Text)
    credit_limit_won: Mapped[int | None] = mapped_column(Integer)
    default_preference_rank: Mapped[int | None] = mapped_column(Integer)
    expires_at: Mapped[date | None] = mapped_column(Date)
    registered_ref: Mapped[str | None] = mapped_column(Text)
    active_from: Mapped[date | None] = mapped_column(Date)
    active_to: Mapped[date | None] = mapped_column(Date)


class CardMonthClose(Base):
    """카드별 월 마감 집계"""

    __tablename__ = "card_month_close"

    user_card_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("user_card.user_card_id"),
        primary_key=True,
    )
    base_month: Mapped[str] = mapped_column(Text, primary_key=True)
    spend_total_won: Mapped[int | None] = mapped_column(Integer)
    benefit_total_won: Mapped[int | None] = mapped_column(Integer)
    credit_used_won: Mapped[int | None] = mapped_column(Integer)
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )
    source_mode: Mapped[str | None] = mapped_column(Text)


class CardPerfMonthClose(Base):
    """카드 혜택 규칙별 월 실적 마감"""

    __tablename__ = "card_perf_month_close"

    user_card_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("user_card.user_card_id"),
        primary_key=True,
    )
    base_month: Mapped[str] = mapped_column(Text, primary_key=True)
    rule_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("benefit_rule.rule_id"),
        primary_key=True,
    )
    eligible_perf_won: Mapped[int | None] = mapped_column(Integer)
    excluded_perf_won: Mapped[int | None] = mapped_column(Integer)
    threshold_met: Mapped[int | None] = mapped_column(Integer)
    rule_version: Mapped[str | None] = mapped_column(Text)
    benefit_used_won: Mapped[int | None] = mapped_column(Integer)
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )
    source_mode: Mapped[str | None] = mapped_column(Text)
