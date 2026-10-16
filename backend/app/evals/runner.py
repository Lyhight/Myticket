import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agent.classifier import RuleBasedTicketClassifier
from app.agent.confirmation import ConfirmationDetector
from app.agent.entity_extractor import RuleBasedEntityExtractor
from app.agent.review import RuleBasedReplyReviewer
from app.evals.statistics import wilson_interval


class MetricResult(BaseModel):
    passed: int = 0
    total: int = 0
    failures: list[dict[str, Any]] = Field(
        default_factory=list
    )

    @property
    def accuracy(self) -> float:
        if self.total == 0:
            return 0.0
        return self.passed / self.total


class EvalReport(BaseModel):
    classification: MetricResult
    entity_extraction: MetricResult
    confirmation: MetricResult
    safety_review: MetricResult

    @property
    def total_cases(self) -> int:
        return sum(
            metric.total
            for metric in self.metrics().values()
        )

    @property
    def overall_accuracy(self) -> float:
        total = self.total_cases
        if total == 0:
            return 0.0
        passed = sum(
            metric.passed
            for metric in self.metrics().values()
        )
        return passed / total

    def metrics(self) -> dict[str, MetricResult]:
        return {
            "classification": self.classification,
            "entity_extraction": self.entity_extraction,
            "confirmation": self.confirmation,
            "safety_review": self.safety_review,
        }

    def summary(self) -> dict[str, Any]:
        return {
            "total_cases": self.total_cases,
            "overall_accuracy": round(
                self.overall_accuracy,
                4,
            ),
            "overall_accuracy_ci95": wilson_interval(
                sum(metric.passed for metric in self.metrics().values()),
                self.total_cases,
            ),
            "metrics": {
                name: {
                    "passed": metric.passed,
                    "total": metric.total,
                    "accuracy": round(metric.accuracy, 4),
                    "accuracy_ci95": wilson_interval(
                        metric.passed,
                        metric.total,
                    ),
                    "failures": metric.failures,
                }
                for name, metric in self.metrics().items()
            },
        }


class AgentEvalRunner:
    def __init__(self) -> None:
        self.classifier = RuleBasedTicketClassifier()
        self.entity_extractor = RuleBasedEntityExtractor()
        self.confirmation_detector = ConfirmationDetector()
        self.reviewer = RuleBasedReplyReviewer()

    async def run_file(self, path: Path) -> EvalReport:
        data = json.loads(path.read_text(encoding="utf-8"))
        return await self.run(data)

    async def run(
        self,
        data: dict[str, list[dict[str, Any]]],
    ) -> EvalReport:
        return EvalReport(
            classification=(
                await self._evaluate_classification(
                    data.get("classification", [])
                )
            ),
            entity_extraction=(
                await self._evaluate_entities(
                    data.get("entity_extraction", [])
                )
            ),
            confirmation=self._evaluate_confirmation(
                data.get("confirmation", [])
            ),
            safety_review=(
                await self._evaluate_safety(
                    data.get("safety_review", [])
                )
            ),
        )

    async def _evaluate_classification(
        self,
        cases: list[dict[str, Any]],
    ) -> MetricResult:
        metric = MetricResult(total=len(cases))
        for case in cases:
            result = await self.classifier.classify(
                title=case["title"],
                content=case["content"],
            )
            actual = {
                "category": result.category,
                "priority": result.priority,
                "intent": result.intent,
            }
            expected = case["expected"]
            if all(
                actual.get(key) == value
                for key, value in expected.items()
            ):
                metric.passed += 1
            else:
                metric.failures.append(
                    {
                        "id": case["id"],
                        "expected": expected,
                        "actual": actual,
                    }
                )
        return metric

    async def _evaluate_entities(
        self,
        cases: list[dict[str, Any]],
    ) -> MetricResult:
        metric = MetricResult(total=len(cases))
        for case in cases:
            result = await self.entity_extractor.extract(
                title=case["title"],
                content=case["content"],
                history=case.get("history"),
            )
            expected = case["expected"]
            if result.entities == expected:
                metric.passed += 1
            else:
                metric.failures.append(
                    {
                        "id": case["id"],
                        "expected": expected,
                        "actual": result.entities,
                    }
                )
        return metric

    def _evaluate_confirmation(
        self,
        cases: list[dict[str, Any]],
    ) -> MetricResult:
        metric = MetricResult(total=len(cases))
        for case in cases:
            actual = self.confirmation_detector.detect(
                case["content"]
            )
            expected = case["expected"]
            if actual == expected:
                metric.passed += 1
            else:
                metric.failures.append(
                    {
                        "id": case["id"],
                        "expected": expected,
                        "actual": actual,
                    }
                )
        return metric

    async def _evaluate_safety(
        self,
        cases: list[dict[str, Any]],
    ) -> MetricResult:
        metric = MetricResult(total=len(cases))
        for case in cases:
            result = await self.reviewer.review(
                reply=case["reply"],
                title="评测工单",
                content="评测消息",
                category="ORDER",
                intent="order_query",
            )
            actual = result.approved
            expected = case["expected_approved"]
            if actual == expected:
                metric.passed += 1
            else:
                metric.failures.append(
                    {
                        "id": case["id"],
                        "expected": expected,
                        "actual": actual,
                        "issues": result.issues,
                    }
                )
        return metric
