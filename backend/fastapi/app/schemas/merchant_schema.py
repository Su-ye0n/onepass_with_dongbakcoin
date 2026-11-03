from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict






# --------- 가맹점 조회 ------------
class MerchantResponse(BaseModel):
    merchant_id: str
    merchant_name: str | None = None
    source_merchant_id: str | None = None
    industry_code: str
    dongbaek_status: str | None = None
    sales_band: str | None = None
    sales_band_basis_at: date | None = None
    is_good_price_shop: bool | None = None
    is_dbplus_shop: bool | None = None
    is_qr_merchant: bool | None = None
    dbplus_discount_rate: Decimal | None = None
    region_code: str | None = None
    source_status: str | None = None

    model_config = ConfigDict(from_attributes=True)