from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MessageResponse(BaseModel):
    id: int
    ticket_id: int
    sender_type: str
    content: str
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )



class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10_000)

    model_config = ConfigDict(str_strip_whitespace=True)
