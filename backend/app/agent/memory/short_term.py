from typing import Any

from pydantic import BaseModel, Field


class ShortTermMemory(BaseModel):
    """仅服务于当前工单任务的工作记忆。"""

    conversation_summary: str | None = None
    active_goal: str | None = None
    known_facts: dict[str, Any] = Field(default_factory=dict)
    missing_information: list[str] = Field(default_factory=list)
    important_tool_results: list[dict[str, Any]] = Field(
        default_factory=list
    )
    long_term_memories: list[dict[str, Any]] = Field(
        default_factory=list
    )
    retrieved_knowledge: list[dict[str, Any]] = Field(
        default_factory=list
    )
