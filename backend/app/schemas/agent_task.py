from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AgentTaskResponse(BaseModel):
    id: int
    idempotency_key: str
    ticket_id: int
    user_id: int
    task_type: str
    payload: dict[str, Any]
    status: str
    attempts: int
    max_attempts: int
    next_retry_at: datetime | None
    last_error: str | None
    locked_by: str | None
    lease_expires_at: datetime | None
    heartbeat_at: datetime | None
    result_message_id: int | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AgentTaskAccepted(BaseModel):
    task_id: int
    status: str
    idempotency_key: str


class AgentTaskStatusResponse(BaseModel):
    id: int
    ticket_id: int
    status: str
    attempts: int
    max_attempts: int
    next_retry_at: datetime | None
    result_message_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
