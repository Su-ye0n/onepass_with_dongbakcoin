
from sqlalchemy import Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CardVerifier(Base):
    """카드 발급 및 검증 정보"""

    __tablename__ = "card_verifier"

    issuance_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )

    owner_id: Mapped[str | None] = mapped_column(Text)
    product_id: Mapped[str | None] = mapped_column(Text)

    expiry_month: Mapped[int | None] = mapped_column(Integer)
    expiry_year: Mapped[int | None] = mapped_column(Integer)

    verifier_hmac: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[str | None] = mapped_column(Text)


class IssuedDemoCard(Base):
    """테스트 환경에서 발급한 모의 카드"""

    __tablename__ = "issued_demo_card"

    issuance_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )

    owner_id: Mapped[str | None] = mapped_column(Text)
    product_id: Mapped[str | None] = mapped_column(Text)

    demo_card_no: Mapped[str | None] = mapped_column(Text)
    demo_expiry: Mapped[str | None] = mapped_column(Text)

    hmac: Mapped[str | None] = mapped_column(Text)
    issue_status: Mapped[str | None] = mapped_column(Text)


class OwnedCard(Base):
    """사용자가 등록한 보유 카드"""

    __tablename__ = "owned_card"

    owned_card_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )

    user_id: Mapped[str | None] = mapped_column(Text)
    issuance_id: Mapped[str | None] = mapped_column(Text)
    product_id: Mapped[str | None] = mapped_column(Text)

    registered_at: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
