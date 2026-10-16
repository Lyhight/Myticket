from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.message import MessageResponse


class TicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=10_000)

    model_config = ConfigDict(str_strip_whitespace=True)


class TicketResponse(BaseModel):
    id: int
    user_id: int

    title: str

    category: str
    priority: str
    intent: str | None
    route_to: str | None

    status: str

    created_at: datetime
    updated_at: datetime
    classification_source: str | None
    classification_attempts: int | None
    classification_latency_ms: float | None
    classification_fallback_used: bool
    classified_at: datetime | None
    model_config = ConfigDict(
        from_attributes=True
    )


class TicketDetailResponse(TicketResponse):
    messages: list[MessageResponse] = Field(default_factory=list)


class TicketRejectRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=2_000)

    model_config = ConfigDict(str_strip_whitespace=True)
