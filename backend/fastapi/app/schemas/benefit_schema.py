
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict




# --------- 카드 혜택 조회 ------------
class BenefitRuleResponse(BaseModel):
    """카드 혜택 규칙 조회 응답"""

    model_config = ConfigDict(from_attributes=True)

    rule_id: str
    product_id: str
    benefit_name: str | None = None
    benefit_type: str | None = None
    rate: Decimal | None = None
    fixed_amount_won: int | None = None
    min_amount_won: int | None = None
    per_tx_cap_won: int | None = None
    monthly_cap_won: int | None = None
    shared_cap_group: str | None = None
    day_condition: str | None = None
    monthly_count_cap: int | None = None
    perf_threshold_won: int | None = None
    perf_basis_code: str | None = None
    reward_unit: str | None = None
    stack_rule: str | None = None
    payment_channel_required: str | None = None
    rounding_mode: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    source_status: str | None = None