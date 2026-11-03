
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Identity, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BenefitRule(Base):
    """카드 상품별 혜택 규칙"""

    __tablename__ = "benefit_rule"

    rule_id: Mapped[str] = mapped_column(Text, primary_key=True)

    product_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("card_product.product_id"),
        nullable=False,
    )

    benefit_name: Mapped[str | None] = mapped_column(Text)
    benefit_type: Mapped[str | None] = mapped_column(Text)
    rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    fixed_amount_won: Mapped[int | None] = mapped_column(Integer)
    min_amount_won: Mapped[int | None] = mapped_column(Integer)
    per_tx_cap_won: Mapped[int | None] = mapped_column(Integer)
    monthly_cap_won: Mapped[int | None] = mapped_column(Integer)
    shared_cap_group: Mapped[str | None] = mapped_column(Text)
    day_condition: Mapped[str | None] = mapped_column(Text)
    monthly_count_cap: Mapped[int | None] = mapped_column(Integer)
    perf_threshold_won: Mapped[int | None] = mapped_column(Integer)
    perf_basis_code: Mapped[str | None] = mapped_column(Text)
    reward_unit: Mapped[str | None] = mapped_column(Text)
    stack_rule: Mapped[str | None] = mapped_column(Text)
    payment_channel_required: Mapped[str | None] = mapped_column(Text)
    rounding_mode: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    source_status: Mapped[str | None] = mapped_column(Text)


class BenefitIndustry(Base):
    """혜택 적용 또는 제외 대상"""

    __tablename__ = "benefit_industry"

    rule_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("benefit_rule.rule_id"),
        primary_key=True,
    )

    target_type: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )

    target_code: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )

    apply_type: Mapped[str | None] = mapped_column(Text)


class BenefitCapTier(Base):
    """카드 이용 실적 구간별 혜택 한도"""

    __tablename__ = "benefit_cap_tier"

    tier_id: Mapped[str] = mapped_column(Text, primary_key=True)

    product_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("card_product.product_id"),
        nullable=False,
    )

    cap_group: Mapped[str | None] = mapped_column(Text)
    perf_min_won: Mapped[int | None] = mapped_column(Integer)
    monthly_cap_won: Mapped[int | None] = mapped_column(Integer)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class CardPerfExclude(Base):
    """카드 전월 실적 산정 시 제외 조건"""

    __tablename__ = "card_perf_exclude"

    exclude_id: Mapped[int] = mapped_column(
        Integer,
        Identity(),
        primary_key=True,
    )

    product_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("card_product.product_id"),
    )

    rule_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("benefit_rule.rule_id"),
    )

    exclude_type: Mapped[str | None] = mapped_column(Text)
    exclude_value: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
