from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserProfileResponse(BaseModel):
    user_id: str
    display_name: str | None
    student_card_id: str | None
    university: str | None
    department: str | None
    phone_number: str | None
    address: str | None
    source_mode: str


class UserProfileUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    student_card_id: str | None = Field(default=None, max_length=64)
    university: str | None = Field(default=None, max_length=120)
    department: str | None = Field(default=None, max_length=120)
    phone_number: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=300)


class WalletAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    wallet_id: str
    charge_won: int
    cashback_won: int
    policy_support_won: int
    balance_won: int


class WalletBalanceResponse(BaseModel):
    user_id: str
    balance_won: int
    wallets: list[WalletAccountResponse]


class WalletTopUpRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=100)
    amount_won: int = Field(gt=0, le=500_000)
    wallet_id: str | None = Field(default=None, min_length=1, max_length=100)


class WalletTopUpResponse(BaseModel):
    tx_id: str
    request_id: str
    user_id: str
    wallet_id: str
    amount_won: int
    balance_won: int
    charge_won: int
    cashback_won: int
    policy_support_won: int
    approval_status: str
    source_mode: str
    event_at: datetime
