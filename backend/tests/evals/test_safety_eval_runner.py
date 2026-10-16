from pathlib import Path

from app.evals.safety_runner import SafetyEvalRunner


async def test_safety_dataset_has_no_false_blocks_or_false_allows() -> None:
    dataset = (
        Path(__file__).parents[3]
        / "benchmark"
        / "datasets"
        / "safety_cases.json"
    )
    report = await SafetyEvalRunner().run_file(dataset)

    assert report.total_cases == 32
    assert report.false_block_rate == 0.0
    assert report.false_allow_rate == 0.0
    assert report.accuracy == 1.0
    assert report.accuracy_ci95[0] < report.accuracy


async def test_safety_eval_builds_confusion_matrix() -> None:
    report = await SafetyEvalRunner().run([
        {"id": "fp", "surface": "output", "text": "好", "expected_blocked": False},
        {"id": "fn", "surface": "input", "text": "普通问题", "expected_blocked": True},
    ])

    assert report.false_positive == 1
    assert report.false_negative == 1
    assert report.false_block_rate == 1.0
    assert report.false_allow_rate == 1.0
