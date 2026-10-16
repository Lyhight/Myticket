from pathlib import Path

from app.evals.task_runner import AgentTaskEvalRunner


async def test_task_eval_dataset_passes() -> None:
    dataset = (
        Path(__file__).parents[3]
        / "benchmark"
        / "datasets"
        / "agent_tasks.json"
    )
    report = await AgentTaskEvalRunner().run_file(dataset)

    assert report.total_cases == 20
    assert report.task_success_rate == 1.0
    assert report.end_to_end is False
    assert report.task_success_rate_ci95[0] < report.task_success_rate
    assert report.failures == []


class FailingExecutor:
    async def execute(self, case):
        return {"category": "OTHER"}


async def test_task_eval_records_field_level_mismatches() -> None:
    report = await AgentTaskEvalRunner(FailingExecutor()).run([
        {
            "id": "failed-task",
            "scenario": "order",
            "expected": {"category": "ORDER"},
        }
    ])

    assert report.task_success_rate == 0.0
    assert report.failures[0]["mismatches"]["category"]["actual"] == "OTHER"
