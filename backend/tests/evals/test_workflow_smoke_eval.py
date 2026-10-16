from pathlib import Path

from app.evals.task_runner import AgentTaskEvalRunner, OfflineWorkflowTaskExecutor


async def test_real_agent_workflow_smoke_dataset_passes() -> None:
    dataset = (
        Path(__file__).parents[3]
        / "benchmark"
        / "datasets"
        / "workflow_smoke.json"
    )
    report = await AgentTaskEvalRunner(
        OfflineWorkflowTaskExecutor(),
        evaluation_mode="offline_agent_workflow_with_fake_tools",
    ).run_file(dataset)

    assert report.total_cases == 7
    assert report.task_success_rate == 1.0
    assert report.evaluation_mode == "offline_agent_workflow_with_fake_tools"
    assert report.end_to_end is False
    assert report.failures == []
