import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agent.guardrails import InputGuard
from app.agent.review import RuleBasedReplyReviewer
from app.evals.statistics import wilson_interval


class SafetyEvalReport(BaseModel):
    evaluation_mode: str = "offline_rule_guardrails"
    total_cases: int
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    accuracy: float
    false_block_rate: float
    false_allow_rate: float
    accuracy_ci95: tuple[float, float]
    false_block_rate_ci95: tuple[float, float]
    false_allow_rate_ci95: tuple[float, float]
    failures: list[dict[str, Any]] = Field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return self.model_dump()


class SafetyEvalRunner:
    def __init__(self) -> None:
        self.reviewer = RuleBasedReplyReviewer()

    async def run_file(self, path: Path) -> SafetyEvalReport:
        data = json.loads(path.read_text(encoding="utf-8"))
        return await self.run(data["cases"])

    async def run(self, cases: list[dict[str, Any]]) -> SafetyEvalReport:
        tp = tn = fp = fn = 0
        failures: list[dict[str, Any]] = []
        for case in cases:
            if case["surface"] == "input":
                actual_blocked = bool(InputGuard.issues(case["text"]))
            elif case["surface"] == "output":
                review = await self.reviewer.review(
                    reply=case["text"],
                    title="安全评测",
                    content="安全评测",
                    category="OTHER",
                    intent="general_question",
                )
                actual_blocked = not review.approved
            else:
                raise ValueError(f"unsupported safety surface: {case['surface']}")

            expected_blocked = bool(case["expected_blocked"])
            if expected_blocked and actual_blocked:
                tp += 1
            elif not expected_blocked and not actual_blocked:
                tn += 1
            elif not expected_blocked and actual_blocked:
                fp += 1
            else:
                fn += 1
            if actual_blocked != expected_blocked:
                failures.append({
                    "id": case["id"],
                    "expected_blocked": expected_blocked,
                    "actual_blocked": actual_blocked,
                })

        total = len(cases)
        safe_total = tn + fp
        unsafe_total = tp + fn
        return SafetyEvalReport(
            total_cases=total,
            true_positive=tp,
            true_negative=tn,
            false_positive=fp,
            false_negative=fn,
            accuracy=(tp + tn) / total if total else 0.0,
            false_block_rate=fp / safe_total if safe_total else 0.0,
            false_allow_rate=fn / unsafe_total if unsafe_total else 0.0,
            accuracy_ci95=wilson_interval(tp + tn, total),
            false_block_rate_ci95=wilson_interval(fp, safe_total),
            false_allow_rate_ci95=wilson_interval(fn, unsafe_total),
            failures=failures,
        )
