
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Merchant(Base):
    """동백전 가맹점 정보"""

    __tablename__ = "merchant"

    # 기본 키
    merchant_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )

    # 가맹점 기본 정보
    merchant_name: Mapped[str | None] = mapped_column(Text)
    source_merchant_id: Mapped[str | None] = mapped_column(Text)

    industry_code: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # 동백전 가맹 여부 및 매출 구간
    dongbaek_status: Mapped[str | None] = mapped_column(Text)
    sales_band: Mapped[str | None] = mapped_column(Text)
    sales_band_basis_at: Mapped[date | None] = mapped_column(Date)

    # 가맹점 유형 및 QR 결제 지원 여부
    is_good_price_shop: Mapped[int | None] = mapped_column(Integer)
    is_dbplus_shop: Mapped[int | None] = mapped_column(Integer)
    is_qr_merchant: Mapped[int | None] = mapped_column(Integer)

    # 동백플러스 할인율
    dbplus_discount_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 4)
    )

    # 지역 및 데이터 출처
    region_code: Mapped[str | None] = mapped_column(Text)
    source_status: Mapped[str | None] = mapped_column(Text)