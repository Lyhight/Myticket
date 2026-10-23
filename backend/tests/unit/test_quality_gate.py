from app.core.config import settings
from app.evals.gate import QualityGate, QualityThresholds


def _agent(score: float) -> dict:
    return {
        "overall_accuracy": score,
        "metrics": {
            "classification": {"accuracy": score},
            "safety_review": {"accuracy": score},
        },
    }


def test_quality_gate_passes_at_baseline() -> None:
    gate = QualityGate(QualityThresholds(
        overall_accuracy=0.9,
        agent_metrics={"classification": 0.9},
        rag_metrics={"recall_at_3": 0.9},
    ))
    report = gate.evaluate(
        agent=_agent(1.0),
        rag={"recall_at_3": 1.0},
    )
    assert report.passed is True
    assert report.violations == []


def test_quality_gate_reports_actual_offline_engine(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_enabled", False)
    gate = QualityGate(QualityThresholds(overall_accuracy=0.9))

    report = gate.evaluate(agent=_agent(1.0))

    assert report.model_name == "rule-based-v1"


def test_quality_gate_blocks_regression() -> None:
    gate = QualityGate(QualityThresholds(
        overall_accuracy=0.95,
        agent_metrics={"safety_review": 1.0},
        rag_metrics={"recall_at_3": 1.0},
    ))
    report = gate.evaluate(
        agent=_agent(0.8),
        rag={"recall_at_3": 0.5},
    )
    assert report.passed is False
    assert len(report.violations) == 3


def test_quality_gate_checks_task_and_safety_regressions() -> None:
    gate = QualityGate(QualityThresholds(
        overall_accuracy=0.9,
        task_metrics={"task_success_rate": 0.95},
        safety_max_metrics={
            "false_block_rate": 0.05,
            "false_allow_rate": 0.0,
        },
    ))
    report = gate.evaluate(
        agent=_agent(1.0),
        tasks={"task_success_rate": 0.8},
        safety={"false_block_rate": 0.1, "false_allow_rate": 0.2},
    )

    assert report.passed is False
    assert len(report.violations) == 3


def test_quality_gate_checks_workflow_regression() -> None:
    gate = QualityGate(QualityThresholds(
        overall_accuracy=0.9,
        workflow_metrics={"task_success_rate": 1.0},
    ))

    report = gate.evaluate(
        agent=_agent(1.0),
        workflow={"task_success_rate": 0.8},
    )

    assert report.passed is False
    assert report.violations == [
        "workflow.task_success_rate=0.8000 is below required 1.0000"
    ]


def test_quality_gate_checks_retail_state_and_policy_metrics() -> None:
    gate = QualityGate(QualityThresholds(
        overall_accuracy=0.9,
        retail_metrics={"final_state_accuracy": 1.0, "pass_pow_k": 1.0},
        retail_max_metrics={"policy_violation_rate": 0.0},
    ))

    report = gate.evaluate(
        agent=_agent(1.0),
        retail={
            "final_state_accuracy": 0.8,
            "pass_pow_k": 0.7,
            "policy_violation_rate": 0.1,
        },
    )

    assert report.passed is False
    assert len(report.violations) == 3
