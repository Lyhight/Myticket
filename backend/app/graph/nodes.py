from typing import Any, Protocol

from app.agent.state import AgentExecution
from app.graph.state import RuntimeState


class DomainAgent(Protocol):
    async def run_with_state(self, **request: Any) -> AgentExecution: ...

    async def resume_from_state(self, **request: Any) -> AgentExecution: ...


class CustomerServiceGraphNodes:
    """Graph nodes with the domain Agent supplied as a dependency."""

    def __init__(self, agent: DomainAgent) -> None:
        self.agent = agent

    async def validate_input(self, state: RuntimeState) -> dict[str, Any]:
        request = state.get("request", {})
        if state.get("mode") == "start" and not str(
            request.get("title", "")
        ).strip():
            raise ValueError("Agent title must not be empty")
        if not str(request.get("content", "")).strip():
            raise ValueError("Agent content must not be empty")
        if (
            state.get("mode") == "resume"
            and request.get("previous_state") is None
        ):
            raise ValueError("Previous Agent state is required when resuming")
        return {}

    async def execute_domain_agent(
        self, state: RuntimeState
    ) -> dict[str, AgentExecution]:
        request = state["request"]
        if state["mode"] == "resume":
            execution = await self.agent.resume_from_state(**request)
        else:
            execution = await self.agent.run_with_state(**request)
        return {"execution": execution}

    @staticmethod
    def mark_outcome(state: RuntimeState, outcome: str) -> dict[str, str]:
        metadata = state["execution"].state.context_metadata
        metadata["orchestrator"] = "langgraph"
        metadata["orchestration_outcome"] = outcome
        return {"outcome": outcome}

    async def mark_completed(self, state: RuntimeState) -> dict[str, str]:
        return self.mark_outcome(state, "completed")

    async def mark_approval(self, state: RuntimeState) -> dict[str, str]:
        return self.mark_outcome(state, "approval")

    async def mark_handoff(self, state: RuntimeState) -> dict[str, str]:
        return self.mark_outcome(state, "handoff")
