
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Identity, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BenefitCategoryMap(Base):
    """가맹점 업종 코드와 표준 카테고리 매핑"""

    __tablename__ = "benefit_category_map"

    __table_args__ = (
        UniqueConstraint(
            "industry_code",
            "valid_from",
            name="uq_benefit_category_map_code_from",
        ),
    )

    map_id: Mapped[int] = mapped_column(
        Integer,
        Identity(),
        primary_key=True,
    )

    industry_code: Mapped[str | None] = mapped_column(Text)
    std_category: Mapped[str | None] = mapped_column(Text)
    screen_group_code: Mapped[str | None] = mapped_column(Text)
    mapping_confidence: Mapped[str | None] = mapped_column(Text)

    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)

    mapping_note: Mapped[str | None] = mapped_column(Text)


class UserCategory(Base):
    """사용자별 카테고리 설정"""

    __tablename__ = "user_category"

    user_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("user.user_id"),
        primary_key=True,
    )

    user_category_code: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )

    label: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int | None] = mapped_column(Integer)
    is_enabled: Mapped[int | None] = mapped_column(Integer)


class UserCategoryPriority(Base):
    """사용자 카테고리별 카드 우선순위"""

    __tablename__ = "user_category_priority"

    priority_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )

    user_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("user.user_id"),
        nullable=False,
    )

    user_category_code: Mapped[str | None] = mapped_column(Text)

    user_card_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("user_card.user_card_id"),
        nullable=False,
    )

    priority_group: Mapped[int | None] = mapped_column(Integer)

    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )

    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )

    setting_version: Mapped[str | None] = mapped_column(Text)
