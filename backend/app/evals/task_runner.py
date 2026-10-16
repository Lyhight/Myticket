import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.agent.classifier import RuleBasedTicketClassifier
from app.agent.confirmation import ConfirmationDetector
from app.agent.entity_extractor import RuleBasedEntityExtractor
from app.agent.guardrails import InputGuard
from app.agent.review import RuleBasedReplyReviewer
from app.agent.customer_service_agent import CustomerServiceAgent
from app.agent.schemas import ClassificationExecution
from app.evals.statistics import wilson_interval


class AgentTaskExecutor(Protocol):
    async def execute(self, case: dict[str, Any]) -> dict[str, Any]: ...


class RuleBasedAgentTaskExecutor:
    """Offline adapter over the same deterministic components used by the app."""

    def __init__(self) -> None:
        self.classifier = RuleBasedTicketClassifier()
        self.extractor = RuleBasedEntityExtractor()
        self.confirmation = ConfirmationDetector()
        self.reviewer = RuleBasedReplyReviewer()

    async def execute(self, case: dict[str, Any]) -> dict[str, Any]:
        title = str(case.get("title", ""))
        content = str(case.get("content", ""))
        classification = await self.classifier.classify(title, content)
        extraction = await self.extractor.extract(
            title=title,
            content=content,
            history=case.get("history"),
        )
        result: dict[str, Any] = {
            "category": classification.category,
            "priority": classification.priority,
            "intent": classification.intent,
            "route_to": classification.route_to,
            "entities": extraction.entities,
            "confirmation": self.confirmation.detect(content),
            "input_blocked": bool(InputGuard.issues(content)),
        }
        if "reply" in case:
            review = await self.reviewer.review(
                reply=str(case["reply"]),
                title=title,
                content=content,
                category=classification.category,
                intent=classification.intent,
            )
            result["reply_approved"] = review.approved
        return result


class _OfflineClassifierService:
    def __init__(self) -> None:
        self.classifier = RuleBasedTicketClassifier()

    async def classify(self, title: str, content: str) -> ClassificationExecution:
        classification = await self.classifier.classify(title, content)
        return ClassificationExecution(
            classification=classification,
            source="rule_based",
            fallback_used=False,
            attempts=1,
            latency_ms=0,
        )


class _FakeBusinessToolExecutor:
    async def execute(self, action, context=None, state=None):
        if action.action != "tool":
            return None
        if action.tool_name == "get_order":
            return {
                "success": True,
                "order": {
                    "order_id": action.tool_args["order_id"],
                    "status": "PAID",
                    "shipping_status": "NOT_SHIPPED",
                },
            }
        if action.tool_name == "get_logistics":
            return {
                "success": True,
                "logistics": {
                    "tracking_number": action.tool_args["tracking_number"],
                    "status": "IN_TRANSIT",
                    "current_location": "测试转运中心",
                },
            }
        if action.tool_name == "check_refund_eligibility":
            return {
                "success": True,
                "eligible": True,
                "requires_human": False,
                "amount": 299.0,
                "reason": "PAID_ORDER_NOT_SHIPPED",
            }
        raise AssertionError(f"unsupported fake tool: {action.tool_name}")


class OfflineWorkflowTaskExecutor:
    """Runs the real Agent state machine with deterministic fake business I/O."""

    def __init__(self) -> None:
        self.agent = CustomerServiceAgent()
        self.agent.classifier = _OfflineClassifierService()
        self.agent.decision_agent = None
        self.agent.tool_executor = _FakeBusinessToolExecutor()
        self.agent.refund_workflow.tool_executor = self.agent.tool_executor
        self.agent.reply_service.generator = None
        self.agent.review_service.primary = None

    async def execute(self, case: dict[str, Any]) -> dict[str, Any]:
        execution = await self.agent.run_with_state(
            title=str(case.get("title", "")),
            content=str(case.get("content", "")),
            history=case.get("history"),
            user_id=1,
            ticket_id=1,
        )
        result = execution.result
        classification = result.classification_execution.classification
        return {
            "category": classification.category,
            "priority": classification.priority,
            "action": result.action.action,
            "tool_name": result.action.tool_name,
            "current_step": execution.state.current_step,
            "review_approved": (
                result.review.approved if result.review is not None else None
            ),
        }


class ScenarioMetric(BaseModel):
    passed: int = 0
    total: int = 0

    @property
    def success_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


class TaskEvalReport(BaseModel):
    evaluation_mode: str = "offline_rule_components"
    end_to_end: bool = False
    total_cases: int
    passed: int
    task_success_rate: float
    task_success_rate_ci95: tuple[float, float]
    scenarios: dict[str, ScenarioMetric]
    failures: list[dict[str, Any]] = Field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        data = self.model_dump()
        data["scenarios"] = {
            name: {
                **metric.model_dump(),
                "success_rate": round(metric.success_rate, 4),
            }
            for name, metric in self.scenarios.items()
        }
        return data


class AgentTaskEvalRunner:
    def __init__(
        self,
        executor: AgentTaskExecutor | None = None,
        *,
        evaluation_mode: str = "offline_rule_components",
        end_to_end: bool = False,
    ) -> None:
        self.executor = executor or RuleBasedAgentTaskExecutor()
        self.evaluation_mode = evaluation_mode
        self.end_to_end = end_to_end

    async def run_file(self, path: Path) -> TaskEvalReport:
        data = json.loads(path.read_text(encoding="utf-8"))
        return await self.run(data["cases"])

    async def run(self, cases: list[dict[str, Any]]) -> TaskEvalReport:
        scenario_counts: dict[str, dict[str, int]] = defaultdict(
            lambda: {"passed": 0, "total": 0}
        )
        failures: list[dict[str, Any]] = []
        passed = 0
        for case in cases:
            actual = await self.executor.execute(case)
            expected = case["expected"]
            mismatches = {
                key: {"expected": value, "actual": actual.get(key)}
                for key, value in expected.items()
                if actual.get(key) != value
            }
            scenario = str(case.get("scenario", "general"))
            scenario_counts[scenario]["total"] += 1
            if not mismatches:
                passed += 1
                scenario_counts[scenario]["passed"] += 1
            else:
                failures.append({
                    "id": case["id"],
                    "scenario": scenario,
                    "mismatches": mismatches,
                })
        total = len(cases)
        return TaskEvalReport(
            evaluation_mode=self.evaluation_mode,
            end_to_end=self.end_to_end,
            total_cases=total,
            passed=passed,
            task_success_rate=passed / total if total else 0.0,
            task_success_rate_ci95=wilson_interval(passed, total),
            scenarios={
                name: ScenarioMetric(**counts)
                for name, counts in scenario_counts.items()
            },
            failures=failures,
        )
