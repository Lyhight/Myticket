

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import CustomerServiceAgentResult
from app.agent.state import AgentState
from app.models.agent_run import AgentRun
from typing import Any
from app.agent.telemetry import build_llm_telemetry
from app.core.logging import get_correlation_id
from app.operations.observability import observe_agent_run


class AgentRunRepository:

    def __init__(
        self,
        db: AsyncSession,
    ):
        self.db = db

    async def create(
        self,
        ticket_id: int,
        result: CustomerServiceAgentResult,
        state: AgentState | None = None,
        rag_trace: dict[str, Any] | None = None,
        memory_trace: dict[str, Any] | None = None,
        context_trace: dict[str, Any] | None = None,
        total_latency_ms: float | None = None,
    ) -> AgentRun:

        execution = (
            result.classification_execution
        )

        action = result.action

        telemetry = build_llm_telemetry(state=state, result=result)
        run = AgentRun(
            ticket_id=ticket_id,
            correlation_id=get_correlation_id(),

            classification_source=(
                execution.source
            ),

            classification_attempts=(
                execution.attempts
            ),

            classification_latency_ms=(
                execution.latency_ms
            ),

            classification_fallback_used=(
                execution.fallback_used
            ),

            action=action.action,

            action_reason=action.reason,

            tool_name=action.tool_name,
            tool_args=action.tool_args,

            tool_result=result.tool_result,

            final_reply=result.reply,

            review_approved=(
                result.review.approved
                if result.review
                else None
            ),

            review_issues=(
                result.review.issues
                if result.review
                else None
            ),

            state_snapshot=(
                state.model_dump(mode="json")
                if state
                else None
            ),

            checkpoint_status=(
                state.current_step
                if state
                else None
            ),
            rag_trace=rag_trace,
            memory_trace=memory_trace,
            context_trace=context_trace,
            total_latency_ms=total_latency_ms,
            model_provider=telemetry["model_provider"],
            model_name=telemetry["model_name"],
            prompt_versions=telemetry["prompt_versions"],
            token_usage=telemetry["token_usage"],
        )

        self.db.add(run)

        await self.db.commit()
        await self.db.refresh(run)

        observe_agent_run(
            result=result,
            rag_trace=rag_trace,
            total_latency_ms=total_latency_ms,
        )

        return run

    async def list_by_ticket(
        self,
        ticket_id: int,
    ) -> list[AgentRun]:

        result = await self.db.execute(
            select(AgentRun)
            .where(
                AgentRun.ticket_id == ticket_id
            )
            .order_by(
                AgentRun.created_at.asc()
            )
        )

        return list(
            result.scalars().all()
        )

    async def get_latest_by_ticket(
        self,
        ticket_id: int,
    ) -> AgentRun | None:
        """
        查询某个工单最近一次 Agent 执行记录。
        """

        result = await self.db.execute(
            select(AgentRun)
            .where(
                AgentRun.ticket_id == ticket_id
            )
            .order_by(
                AgentRun.created_at.desc()
            )
            .limit(1)
        )

        return result.scalar_one_or_none()

    async def get_latest_state_by_ticket(
        self,
        ticket_id: int,
    ) -> AgentState | None:
        latest_run = await self.get_latest_by_ticket(
            ticket_id
        )

        if (
            latest_run is None
            or latest_run.state_snapshot is None
        ):
            return None

        return AgentState.model_validate(
            latest_run.state_snapshot
        )
