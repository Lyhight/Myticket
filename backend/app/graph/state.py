from typing import Any, Literal, TypedDict

from app.agent.state import AgentExecution


class RuntimeState(TypedDict, total=False):
    """State owned by the outer orchestration graph for one invocation."""

    mode: Literal["start", "resume"]
    request: dict[str, Any]
    execution: AgentExecution
    outcome: Literal["completed", "approval", "handoff"]
