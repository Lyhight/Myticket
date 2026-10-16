from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun


class AgentOperationsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def snapshot(self, *, hours: int = 24) -> dict[str, Any]:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
        result = await self.db.execute(
            select(AgentRun).where(AgentRun.created_at >= since)
        )
        runs = list(result.scalars().all())
        latencies = sorted(
            float(run.total_latency_ms)
            for run in runs
            if run.total_latency_ms is not None
        )
        failures = [run for run in runs if run.checkpoint_status == "failed"]
        escalations = [run for run in runs if run.action == "escalate_to_human"]
        tool_calls = [run for run in runs if run.tool_name]
        tool_failures = [
            run for run in tool_calls
            if isinstance(run.tool_result, dict)
            and run.tool_result.get("success") is False
        ]
        rag_fallbacks = [
            run for run in runs
            if isinstance(run.rag_trace, dict)
            and run.rag_trace.get("fallback_used") is True
        ]

        def ratio(value: int) -> float:
            return round(value / len(runs), 4) if runs else 0.0

        p95_index = max(0, ceil(len(latencies) * 0.95) - 1)
        return {
            "window_hours": hours,
            "run_count": len(runs),
            "failure_count": len(failures),
            "failure_rate": ratio(len(failures)),
            "escalation_count": len(escalations),
            "escalation_rate": ratio(len(escalations)),
            "tool_call_count": len(tool_calls),
            "tool_failure_count": len(tool_failures),
            "rag_fallback_count": len(rag_fallbacks),
            "average_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
            "p95_latency_ms": round(latencies[p95_index], 3) if latencies else 0.0,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def alerts(metrics: dict[str, Any]) -> list[dict[str, str]]:
        alerts: list[dict[str, str]] = []
        if metrics["run_count"] >= 5 and metrics["failure_rate"] >= 0.2:
            alerts.append({"level": "critical", "code": "HIGH_FAILURE_RATE", "message": "Agent 失败率达到 20%"})
        if metrics["run_count"] >= 5 and metrics["escalation_rate"] >= 0.5:
            alerts.append({"level": "warning", "code": "HIGH_ESCALATION_RATE", "message": "转人工比例达到 50%"})
        if metrics["p95_latency_ms"] >= 10000:
            alerts.append({"level": "warning", "code": "HIGH_P95_LATENCY", "message": "Agent P95 延迟超过 10 秒"})
        if metrics["tool_failure_count"] >= 3:
            alerts.append({"level": "critical", "code": "TOOL_FAILURE_BURST", "message": "工具失败次数达到 3 次"})
        return alerts
