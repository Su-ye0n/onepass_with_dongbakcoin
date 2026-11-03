from pydantic import BaseModel, ConfigDict
from datetime import date
from pydantic import Field, model_validator




# --------- 카드 상품 조회 응답------------
class CardProductResponse(BaseModel):
    """카드 상품 조회 응답"""

    model_config = ConfigDict(from_attributes=True)

    product_id: str
    product_name: str
    issuer: str | None = None
    card_type: str | None = None
    product_status: str | None = None
    terms_version: str | None = None
    source_status: str | None = None
    source_ref: str | None = None




# --------- 사용자 보유 카드 조회 응답------------
class UserCardResponse(BaseModel):
    """사용자 보유 카드 조회 응답"""

    model_config = ConfigDict(from_attributes=True)

    user_card_id: str
    user_id: str
    product_id: str
    db_wallet_id: str | None = None
    linked_account_id: str | None = None
    card_status: str | None = None
    credit_limit_won: int | None = None
    default_preference_rank: int | None = None
    expires_at: date | None = None
    registered_ref: str | None = None
    active_from: date | None = None
    active_to: date | None = None



# --------- 사용자 카드 등록 요청 ------------
class UserCardCreateRequest(BaseModel):
    """사용자 보유 카드 등록 요청"""

    product_id: str











# --------- 사용자 카드 우선순위 설정 ------------
class CardPriorityItem(BaseModel):
    """카드 한 장의 우선순위"""

    user_card_id: str = Field(min_length=1)
    priority: int = Field(ge=1)


class CardPriorityUpdateRequest(BaseModel):
    """사용자 카드 우선순위 일괄 변경 요청"""

    cards: list[CardPriorityItem] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_priorities(self):
        card_ids = [card.user_card_id for card in self.cards]
        priorities = [card.priority for card in self.cards]

        if len(card_ids) != len(set(card_ids)):
            raise ValueError("중복된 카드 ID가 있습니다.")

        if len(priorities) != len(set(priorities)):
            raise ValueError("중복된 우선순위가 있습니다.")

        return self