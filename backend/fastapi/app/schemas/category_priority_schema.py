from pydantic import BaseModel, ConfigDict, Field, model_validator


class CategoryPriorityItem(BaseModel):
    """카테고리별 카드 우선순위 한 건"""

    user_category_code: str = Field(min_length=1)
    user_card_id: str = Field(min_length=1)
    priority_group: int = Field(ge=1)


class CategoryPriorityUpdateRequest(BaseModel):
    """카테고리별 카드 우선순위 일괄 저장 요청"""

    priorities: list[CategoryPriorityItem]

    @model_validator(mode="after")
    def validate_priorities(self):
        pairs = [
            (item.user_category_code, item.priority_group)
            for item in self.priorities
        ]

        if len(pairs) != len(set(pairs)):
            raise ValueError(
                "같은 카테고리에 중복된 우선순위가 있습니다."
            )

        card_pairs = [
            (item.user_category_code, item.user_card_id)
            for item in self.priorities
        ]

        if len(card_pairs) != len(set(card_pairs)):
            raise ValueError(
                "같은 카테고리에 동일한 카드가 중복되었습니다."
            )

        return self


class CategoryPriorityResponse(BaseModel):
    """카테고리별 카드 우선순위 응답"""

    model_config = ConfigDict(from_attributes=True)

    priority_id: str
    user_id: str
    user_category_code: str
    user_card_id: str
    priority_group: int | None = None