from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FeedbackCreate(BaseModel):
    ticket_id: int = Field(gt=0)
    message_id: int = Field(gt=0)
    rating: Literal["UP", "DOWN"]
    comment: str | None = Field(default=None, max_length=2_000)

    model_config = ConfigDict(str_strip_whitespace=True)


class FeedbackResponse(BaseModel):
    id: int
    ticket_id: int
    message_id: int
    agent_run_id: int | None
    user_id: int
    rating: str
    comment: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KnowledgeGapResponse(BaseModel):
    id: int
    ticket_id: int | None
    agent_run_id: int | None
    feedback_id: int | None
    question: str
    suggested_answer: str | None
    source: str
    reason: str
    status: str
    occurrence_count: int
    reviewer_note: str | None
    reviewed_by: int | None
    reviewed_at: datetime | None
    knowledge_document_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KnowledgeGapApprove(BaseModel):
    approved_answer: str = Field(min_length=5, max_length=20_000)
    title: str | None = Field(default=None, max_length=255)
    reviewer_note: str | None = Field(default=None, max_length=2_000)

    model_config = ConfigDict(str_strip_whitespace=True)


class KnowledgeGapReject(BaseModel):
    reviewer_note: str = Field(min_length=2, max_length=2_000)

    model_config = ConfigDict(str_strip_whitespace=True)
