import json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agent.customer_service_agent import CustomerServiceAgent
from app.agent.schemas import ClassificationExecution
from app.agent.classifier import RuleBasedTicketClassifier
from app.evals.statistics import wilson_interval


class _OfflineClassifierService:
    def __init__(self) -> None:
        self.classifier = RuleBasedTicketClassifier()

    async def classify(self, title: str, content: str) -> ClassificationExecution:
        return ClassificationExecution(
            classification=await self.classifier.classify(title, content),
            source="rule_based",
            fallback_used=False,
            attempts=1,
            latency_ms=0,
        )


class StatefulRetailEnvironment:
    """A fresh, mutable business environment for one benchmark trial."""

    def __init__(self, initial_state: dict[str, Any]) -> None:
        self.orders = {
            str(order["order_id"]): deepcopy(order)
            for order in initial_state.get("orders", [])
        }
        self.logistics = {
            str(item["tracking_number"]): deepcopy(item)
            for item in initial_state.get("logistics", [])
        }
        self.refunds = deepcopy(initial_state.get("refunds", []))
        self.calls: list[dict[str, Any]] = []
        self.policy_violations: list[str] = []

    async def execute(self, action, context=None, state=None):
        if action.action != "tool":
            return None
        name = str(action.tool_name)
        arguments = deepcopy(action.tool_args)
        self.calls.append({"name": name, "arguments": arguments})

        if context is None:
            self.policy_violations.append("missing_trusted_tool_context")
            return {"success": False, "error": "missing_context"}

        if name == "get_order":
            order = self.orders.get(str(arguments.get("order_id")))
            if order is None or order.get("user_id") != context.user_id:
                return {"success": False, "error": "order_not_found"}
            return {"success": True, "order": self._public_order(order)}

        if name == "get_logistics":
            item = self.logistics.get(str(arguments.get("tracking_number")))
            if item is None or item.get("user_id") != context.user_id:
                return {"success": False, "error": "logistics_not_found"}
            return {"success": True, "logistics": deepcopy(item)}

        if name == "check_refund_eligibility":
            order = self.orders.get(str(arguments.get("order_id")))
            if order is None or order.get("user_id") != context.user_id:
                return {"success": False, "error": "order_not_found"}
            if order.get("status") == "REFUNDED":
                return self._eligibility(order, False, False, "ALREADY_REFUNDED")
            if order.get("shipping_status") != "NOT_SHIPPED":
                return self._eligibility(order, False, True, "ORDER_ALREADY_SHIPPED")
            return self._eligibility(order, True, False, "PAID_ORDER_NOT_SHIPPED")

        if name == "create_refund_request":
            return self._create_refund(arguments, context.user_id)

        self.policy_violations.append(f"unknown_tool:{name}")
        return {"success": False, "error": "unknown_tool"}

    def _create_refund(self, arguments: dict[str, Any], user_id: int) -> dict[str, Any]:
        order_id = str(arguments.get("order_id"))
        order = self.orders.get(order_id)
        if arguments.get("confirmed") is not True:
            self.policy_violations.append("refund_without_confirmation")
            return {"success": False, "error": "confirmation_required"}
        if order is None or order.get("user_id") != user_id:
            self.policy_violations.append("unauthorized_refund_attempt")
            return {"success": False, "error": "order_not_found"}
        if order.get("status") == "REFUNDED" or order.get("shipping_status") != "NOT_SHIPPED":
            self.policy_violations.append("ineligible_refund_attempt")
            return {"success": False, "error": "refund_not_eligible"}
        key = str(arguments.get("idempotency_key", ""))
        existing = next((item for item in self.refunds if item.get("idempotency_key") == key), None)
        if existing is None:
            existing = {
                "request_no": f"RF-{user_id}-{order_id}",
                "order_id": order_id,
                "user_id": user_id,
                "status": "PENDING",
                "amount": float(order["amount"]),
                "idempotency_key": key,
            }
            self.refunds.append(existing)
        return {"success": True, "refund": deepcopy(existing)}

    @staticmethod
    def _public_order(order: dict[str, Any]) -> dict[str, Any]:
        return {
            key: deepcopy(value)
            for key, value in order.items()
            if key != "user_id"
        }

    @staticmethod
    def _eligibility(
        order: dict[str, Any], eligible: bool, requires_human: bool, reason: str
    ) -> dict[str, Any]:
        return {
            "success": True,
            "eligible": eligible,
            "requires_human": requires_human,
            "amount": float(order["amount"]),
            "reason": reason,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "orders": sorted(deepcopy(list(self.orders.values())), key=lambda x: str(x["order_id"])),
            "logistics": sorted(
                deepcopy(list(self.logistics.values())),
                key=lambda x: str(x["tracking_number"]),
            ),
            "refunds": sorted(deepcopy(self.refunds), key=lambda x: str(x["request_no"])),
        }


class RetailScenarioMetric(BaseModel):
    passed: int = 0
    total: int = 0

    @property
    def success_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


class RetailEvalReport(BaseModel):
    evaluation_mode: str = "tau_bench_inspired_offline_retail"
    official_tau_bench: bool = False
    end_to_end: bool = False
    total_tasks: int
    trials_per_task: int
    total_trials: int
    successful_trials: int
    task_success_rate: float
    task_success_rate_ci95: tuple[float, float]
    pass_pow_k: float
    final_state_accuracy: float
    tool_selection_accuracy: float
    tool_argument_accuracy: float
    final_action_accuracy: float
    policy_violation_rate: float
    scenarios: dict[str, RetailScenarioMetric]
    failures: list[dict[str, Any]] = Field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        data = self.model_dump()
        data["scenarios"] = {
            name: {**metric.model_dump(), "success_rate": round(metric.success_rate, 4)}
            for name, metric in self.scenarios.items()
        }
        return data


class RetailToolEvalRunner:
    """State-based Tool-Agent evaluation with repeat-trial reliability metrics."""

    async def run_file(self, path: Path) -> RetailEvalReport:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return await self.run(payload["cases"], int(payload.get("trials_per_task", 1)))

    async def run(
        self, cases: list[dict[str, Any]], trials_per_task: int = 1
    ) -> RetailEvalReport:
        if trials_per_task < 1:
            raise ValueError("trials_per_task must be at least 1")
        scenario_counts: dict[str, dict[str, int]] = defaultdict(
            lambda: {"passed": 0, "total": 0}
        )
        failures: list[dict[str, Any]] = []
        trial_successes = final_matches = tool_matches = argument_matches = 0
        action_matches = violating_trials = 0
        task_all_passed = 0

        for case in cases:
            case_results: list[bool] = []
            scenario = str(case.get("scenario", "general"))
            scenario_counts[scenario]["total"] += 1
            for trial in range(1, trials_per_task + 1):
                result = await self._run_trial(case)
                final_matches += int(result["final_state_match"])
                tool_matches += int(result["tool_selection_match"])
                argument_matches += int(result["tool_argument_match"])
                action_matches += int(result["final_action_match"])
                violating_trials += int(bool(result["policy_violations"]))
                passed = all(
                    (
                        result["final_state_match"],
                        result["tool_selection_match"],
                        result["tool_argument_match"],
                        not result["policy_violations"],
                        result["final_action_match"],
                    )
                )
                trial_successes += int(passed)
                case_results.append(passed)
                if not passed:
                    failures.append({
                        "id": case["id"],
                        "scenario": scenario,
                        "trial": trial,
                        **result,
                    })
            if all(case_results):
                task_all_passed += 1
                scenario_counts[scenario]["passed"] += 1

        total_trials = len(cases) * trials_per_task
        denominator = total_trials or 1
        return RetailEvalReport(
            total_tasks=len(cases),
            trials_per_task=trials_per_task,
            total_trials=total_trials,
            successful_trials=trial_successes,
            task_success_rate=trial_successes / denominator if total_trials else 0.0,
            task_success_rate_ci95=wilson_interval(trial_successes, total_trials),
            pass_pow_k=task_all_passed / len(cases) if cases else 0.0,
            final_state_accuracy=final_matches / denominator if total_trials else 0.0,
            tool_selection_accuracy=tool_matches / denominator if total_trials else 0.0,
            tool_argument_accuracy=argument_matches / denominator if total_trials else 0.0,
            final_action_accuracy=action_matches / denominator if total_trials else 0.0,
            policy_violation_rate=violating_trials / denominator if total_trials else 0.0,
            scenarios={name: RetailScenarioMetric(**counts) for name, counts in scenario_counts.items()},
            failures=failures,
        )

    async def _run_trial(self, case: dict[str, Any]) -> dict[str, Any]:
        environment = StatefulRetailEnvironment(case.get("initial_state", {}))
        agent = CustomerServiceAgent()
        agent.classifier = _OfflineClassifierService()
        agent.decision_agent = None
        agent.tool_executor = environment
        agent.refund_workflow.tool_executor = environment
        agent.reply_service.generator = None
        agent.review_service.primary = None
        execution = None
        history: list[dict[str, str]] = []
        turns = case.get("turns", [])
        for index, turn in enumerate(turns):
            content = str(turn["content"])
            if index > 0 and execution and execution.state.current_step == "waiting_for_confirmation":
                execution = await agent.resume_from_state(
                    previous_state=execution.state,
                    content=content,
                    user_id=int(case["user_id"]),
                    ticket_id=int(case.get("ticket_id", 1)),
                )
            else:
                execution = await agent.run_with_state(
                    title=str(case.get("title", "零售客服任务")),
                    content=content,
                    history=history,
                    previous_state=execution.state if execution else None,
                    user_id=int(case["user_id"]),
                    ticket_id=int(case.get("ticket_id", 1)),
                )
            history.extend([
                {"role": "user", "content": content},
                {"role": "assistant", "content": execution.result.reply},
            ])
        if execution is None:
            raise ValueError(f"case {case.get('id')} has no turns")

        expected_calls = case.get("expected_tool_calls", [])
        actual_names = [call["name"] for call in environment.calls]
        expected_names = [call["name"] for call in expected_calls]
        args_match = len(expected_calls) == len(environment.calls) and all(
            (
                self._contains(actual["arguments"], expected.get("arguments", {}))
                if expected.get("allow_extra_arguments", False)
                else actual["arguments"] == expected.get("arguments", {})
            )
            for actual, expected in zip(environment.calls, expected_calls)
        )
        expected_action = case.get("expected_final_action", {})
        actual_action = {
            "action": execution.result.action.action,
            "tool_name": execution.result.action.tool_name,
            "current_step": execution.state.current_step,
        }
        return {
            "final_state_match": self._contains(
                environment.snapshot(), case.get("expected_final_state", {})
            ),
            "tool_selection_match": actual_names == expected_names,
            "tool_argument_match": args_match,
            "final_action_match": self._contains(actual_action, expected_action),
            "policy_violations": environment.policy_violations,
            "expected_tool_calls": expected_calls,
            "actual_tool_calls": environment.calls,
            "expected_final_state": case.get("expected_final_state", {}),
            "actual_final_state": environment.snapshot(),
            "expected_final_action": expected_action,
            "actual_final_action": actual_action,
        }

    @classmethod
    def _contains(cls, actual: Any, expected: Any) -> bool:
        if isinstance(expected, dict):
            return isinstance(actual, dict) and all(
                key in actual and cls._contains(actual[key], value)
                for key, value in expected.items()
            )
        if isinstance(expected, list):
            return isinstance(actual, list) and len(actual) == len(expected) and all(
                cls._contains(left, right) for left, right in zip(actual, expected)
            )
        return actual == expected
