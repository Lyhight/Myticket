from pathlib import Path

from app.evals.runner import AgentEvalRunner


async def test_offline_eval_baseline() -> None:
    dataset = (
        Path(__file__).parents[2]
        / "evals"
        / "agent_cases.json"
    )
    report = await AgentEvalRunner().run_file(dataset)

    assert report.total_cases == 25
    assert report.classification.accuracy == 1.0
    assert report.entity_extraction.accuracy == 1.0
    assert report.confirmation.accuracy == 1.0
    assert report.safety_review.accuracy == 1.0
    assert report.overall_accuracy == 1.0
