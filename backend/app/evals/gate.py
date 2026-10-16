import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agent.versioning import EVAL_DATASET_VERSION, PROMPT_VERSIONS
from app.core.config import settings


class QualityThresholds(BaseModel):
    overall_accuracy: float = 0.95
    agent_metrics: dict[str, float] = Field(default_factory=dict)
    rag_metrics: dict[str, float] = Field(default_factory=dict)
    task_metrics: dict[str, float] = Field(default_factory=dict)
    workflow_metrics: dict[str, float] = Field(default_factory=dict)
    safety_max_metrics: dict[str, float] = Field(default_factory=dict)


class QualityGateReport(BaseModel):
    passed: bool
    dataset_version: str
    model_name: str
    prompt_versions: dict[str, str]
    violations: list[str]
    agent: dict[str, Any]
    rag: dict[str, Any] | None = None
    tasks: dict[str, Any] | None = None
    workflow: dict[str, Any] | None = None
    safety: dict[str, Any] | None = None


class QualityGate:
    def __init__(self, thresholds: QualityThresholds) -> None:
        self.thresholds = thresholds

    @classmethod
    def from_file(cls, path: Path) -> "QualityGate":
        return cls(QualityThresholds.model_validate_json(path.read_text(encoding="utf-8")))

    def evaluate(
        self,
        *,
        agent: dict[str, Any],
        rag: dict[str, Any] | None = None,
        tasks: dict[str, Any] | None = None,
        workflow: dict[str, Any] | None = None,
        safety: dict[str, Any] | None = None,
    ) -> QualityGateReport:
        violations: list[str] = []
        self._check(
            "agent.overall_accuracy",
            float(agent.get("overall_accuracy", 0)),
            self.thresholds.overall_accuracy,
            violations,
        )
        agent_metrics = agent.get("metrics", {})
        for name, minimum in self.thresholds.agent_metrics.items():
            actual = float(agent_metrics.get(name, {}).get("accuracy", 0))
            self._check(f"agent.{name}", actual, minimum, violations)
        if self.thresholds.rag_metrics:
            if rag is None:
                violations.append("rag report is required")
            else:
                for name, minimum in self.thresholds.rag_metrics.items():
                    self._check(
                        f"rag.{name}",
                        float(rag.get(name, 0)),
                        minimum,
                        violations,
                    )
        self._check_optional_minimums(
            section="tasks",
            actual=tasks,
            thresholds=self.thresholds.task_metrics,
            violations=violations,
        )
        self._check_optional_minimums(
            section="workflow",
            actual=workflow,
            thresholds=self.thresholds.workflow_metrics,
            violations=violations,
        )
        if self.thresholds.safety_max_metrics:
            if safety is None:
                violations.append("safety report is required")
            else:
                for name, maximum in self.thresholds.safety_max_metrics.items():
                    actual = float(safety.get(name, 1))
                    if actual > maximum:
                        violations.append(
                            f"safety.{name}={actual:.4f} is above allowed "
                            f"{maximum:.4f}"
                        )
        return QualityGateReport(
            passed=not violations,
            dataset_version=EVAL_DATASET_VERSION,
            model_name=(
                settings.qwen_model
                if settings.llm_enabled
                else "rule-based-v1"
            ),
            prompt_versions=dict(PROMPT_VERSIONS),
            violations=violations,
            agent=agent,
            rag=rag,
            tasks=tasks,
            workflow=workflow,
            safety=safety,
        )

    @classmethod
    def _check_optional_minimums(
        cls,
        *,
        section: str,
        actual: dict[str, Any] | None,
        thresholds: dict[str, float],
        violations: list[str],
    ) -> None:
        if not thresholds:
            return
        if actual is None:
            violations.append(f"{section} report is required")
            return
        for name, minimum in thresholds.items():
            cls._check(
                f"{section}.{name}",
                float(actual.get(name, 0)),
                minimum,
                violations,
            )

    @staticmethod
    def _check(
        name: str,
        actual: float,
        minimum: float,
        violations: list[str],
    ) -> None:
        if actual < minimum:
            violations.append(
                f"{name}={actual:.4f} is below required {minimum:.4f}"
            )
