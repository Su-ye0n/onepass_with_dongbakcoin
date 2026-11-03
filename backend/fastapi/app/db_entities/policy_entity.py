
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Identity, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DbPolicy(Base):
    """동백전 정책 정보"""

    __tablename__ = "db_policy"

    policy_id: Mapped[str] = mapped_column(Text, primary_key=True)
    policy_name: Mapped[str | None] = mapped_column(Text)
    policy_mode: Mapped[str | None] = mapped_column(Text)

    monthly_cashback_base_cap_won: Mapped[int | None] = mapped_column(Integer)
    monthly_charge_cap_won: Mapped[int | None] = mapped_column(Integer)
    holding_balance_cap_won: Mapped[int | None] = mapped_column(Integer)

    funding_order: Mapped[str | None] = mapped_column(Text)
    rounding_mode: Mapped[str | None] = mapped_column(Text)

    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)

    source_status: Mapped[str | None] = mapped_column(Text)
    policy_note: Mapped[str | None] = mapped_column(Text)


class DbPolicyRate(Base):
    """동백전 정책별 가맹점 매출 구간 캐시백 비율"""

    __tablename__ = "db_policy_rate"

    policy_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("db_policy.policy_id"),
        primary_key=True,
    )

    sales_band: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )

    cashback_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 5)
    )

    eligible_funding_bucket: Mapped[str | None] = mapped_column(Text)


class DbPolicyBonus(Base):
    """동백전 추가 혜택 정책"""

    __tablename__ = "db_policy_bonus"

    bonus_id: Mapped[int] = mapped_column(
        Integer,
        Identity(),
        primary_key=True,
    )

    policy_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("db_policy.policy_id"),
        nullable=False,
    )

    bonus_name: Mapped[str | None] = mapped_column(Text)
    bonus_type: Mapped[str | None] = mapped_column(Text)
    sales_band: Mapped[str | None] = mapped_column(Text)
    rate_mode: Mapped[str | None] = mapped_column(Text)

    bonus_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 5)
    )

    fixed_won: Mapped[int | None] = mapped_column(Integer)
    max_benefit_won: Mapped[int | None] = mapped_column(Integer)

    payment_channel_required: Mapped[str | None] = mapped_column(Text)
    required_merchant_flag: Mapped[str | None] = mapped_column(Text)

    coupon_required: Mapped[int | None] = mapped_column(Integer)
    min_payment_won: Mapped[int | None] = mapped_column(Integer)

    excluded_category_codes: Mapped[str | None] = mapped_column(Text)
    funding_bucket_scope: Mapped[str | None] = mapped_column(Text)
    stack_rule: Mapped[str | None] = mapped_column(Text)

    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)

    source_status: Mapped[str | None] = mapped_column(Text)
