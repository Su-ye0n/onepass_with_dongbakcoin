from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserIdentityCardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    identity_card_id: str
    user_id: str
    card_type: str
    issuer_name: str
    title: str
    holder_name: str
    subtitle: str
    status: str
    service_summary: str
    credential_label: str
    source_mode: str
    created_at: datetime
