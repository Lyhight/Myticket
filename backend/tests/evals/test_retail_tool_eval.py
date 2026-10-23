from pathlib import Path

from app.evals.retail_runner import RetailToolEvalRunner


async def test_stateful_retail_tool_dataset_passes() -> None:
    dataset = (
        Path(__file__).parents[3]
        / "benchmark"
        / "datasets"
        / "retail_tool_tasks.json"
    )

    report = await RetailToolEvalRunner().run_file(dataset)

    assert report.total_tasks == 10
    assert report.total_trials == 30
    assert report.trials_per_task == 3
    assert report.task_success_rate == 1.0
    assert report.pass_pow_k == 1.0
    assert report.final_state_accuracy == 1.0
    assert report.tool_selection_accuracy == 1.0
    assert report.tool_argument_accuracy == 1.0
    assert report.final_action_accuracy == 1.0
    assert report.policy_violation_rate == 0.0
    assert report.official_tau_bench is False
    assert report.end_to_end is False
    assert report.failures == []


async def test_retail_tool_eval_detects_wrong_final_state() -> None:
    case = {
        "id": "wrong-state",
        "scenario": "refund",
        "user_id": 1,
        "title": "申请退款",
        "turns": [{"content": "我想退款"}],
        "initial_state": {"refunds": []},
        "expected_tool_calls": [],
        "expected_final_state": {"refunds": [{"request_no": "never-created"}]},
        "expected_final_action": {"action": "ask_user"},
    }

    report = await RetailToolEvalRunner().run([case])

    assert report.task_success_rate == 0.0
    assert report.final_state_accuracy == 0.0
    assert report.failures[0]["final_state_match"] is False
