from typing import Literal

from app.graph.state import RuntimeState


GraphOutcome = Literal["completed", "approval", "handoff"]


def route_execution(state: RuntimeState) -> GraphOutcome:
    """Route by persisted domain state, without duplicating domain rules."""

    agent_state = state["execution"].state
    if (
        agent_state.current_step == "waiting_for_human"
        and agent_state.pending_action is not None
    ):
        return "approval"
    if agent_state.current_step == "waiting_for_human":
        return "handoff"
    return "completed"
