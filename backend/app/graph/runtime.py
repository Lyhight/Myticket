from typing import Any

from app.agent.state import AgentExecution
from app.graph.build import build_customer_service_graph
from app.graph.nodes import DomainAgent


class LangGraphCustomerServiceRuntime:
    """Public runtime for starting and resuming the customer-service graph."""

    def __init__(self, agent: DomainAgent) -> None:
        self.agent = agent
        self.graph = build_customer_service_graph(agent)

    async def run_with_state(self, **request: Any) -> AgentExecution:
        result = await self.graph.ainvoke(
            {"mode": "start", "request": request}
        )
        return result["execution"]

    async def resume_from_state(self, **request: Any) -> AgentExecution:
        result = await self.graph.ainvoke(
            {"mode": "resume", "request": request}
        )
        return result["execution"]
