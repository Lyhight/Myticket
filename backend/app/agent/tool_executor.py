import asyncio
import logging
from time import perf_counter
from typing import Any

from app.agent.policy import ActionPolicy
from app.agent.schemas import AgentAction
from app.agent.state import AgentState
from app.agent.tool_context import ToolExecutionContext
from app.tools import tool_registry


logger = logging.getLogger(__name__)


class ToolExecutor:
    def __init__(self) -> None:
        self.policy = ActionPolicy()

    async def execute(
        self,
        action: AgentAction,
        context: ToolExecutionContext | None = None,
        state: AgentState | None = None,
    ) -> dict[str, Any] | None:
        if action.action in {
            "direct_reply",
            "ask_user",
            "request_confirmation",
            "escalate_to_human",
        }:
            return None

        if action.action != "tool":
            raise ValueError(f"Unsupported action: {action.action}")
        if not action.tool_name:
            return self._error("MISSING_TOOL_NAME", "Tool name is missing")
        if not tool_registry.exists(action.tool_name):
            return self._error(
                "TOOL_NOT_FOUND",
                f"Tool '{action.tool_name}' is not registered.",
            )

        trusted_human_approval = bool(
            context and context.human_approved
        )
        decision = self.policy.evaluate(
            action,
            state,
            trusted_human_approval=trusted_human_approval,
        )
        if not decision.allowed:
            return self._error(
                "POLICY_DENIED",
                "; ".join(decision.issues),
            )

        definition = tool_registry.definition(action.tool_name)
        # 身份字段永远不接受模型值，校验前直接移除，随后由后端注入。
        untrusted_args = {
            key: value
            for key, value in action.tool_args.items()
            if key not in {"user_id", "ticket_id", "human_approved"}
        }
        validated_args, validation_errors = (
            tool_registry.validate_arguments(
                action.tool_name,
                untrusted_args,
            )
        )
        if validated_args is None:
            return {
                **self._error(
                    "INVALID_TOOL_ARGUMENTS",
                    "Tool arguments failed schema validation.",
                ),
                "details": validation_errors,
            }

        if definition.requires_user_context:
            if context is None:
                return self._error(
                    "MISSING_USER_CONTEXT",
                    "Protected tool requires trusted user context.",
                )
            validated_args["user_id"] = context.user_id

        if definition.risk_level == "high":
            validated_args["human_approved"] = (
                trusted_human_approval
            )

        attempts = 0
        started = perf_counter()
        last_error: Exception | None = None
        total_attempts = definition.max_retries + 1

        for attempt in range(1, total_attempts + 1):
            attempts = attempt
            try:
                result = await asyncio.wait_for(
                    definition.function(**validated_args),
                    timeout=definition.timeout_seconds,
                )
                return self._with_audit(
                    result,
                    tool_name=action.tool_name,
                    attempts=attempts,
                    started=started,
                )
            except asyncio.TimeoutError as exc:
                last_error = exc
                logger.warning(
                    "tool_timeout tool=%s attempt=%s",
                    action.tool_name,
                    attempt,
                )
                if definition.risk_level == "high":
                    break
            except TypeError as exc:
                logger.warning(
                    "tool_argument_type_error tool=%s error=%s",
                    action.tool_name,
                    exc,
                )
                return self._error(
                    "INVALID_TOOL_ARGUMENTS",
                    "Tool arguments could not be processed.",
                    action.tool_name,
                    attempts,
                    started,
                )
            except Exception as exc:
                last_error = exc
                logger.exception(
                    "tool_execution_failed tool=%s attempt=%s",
                    action.tool_name,
                    attempt,
                )
                if definition.risk_level == "high":
                    break

            if attempt < total_attempts:
                await asyncio.sleep(0.1 * attempt)

        error_code = (
            "TOOL_TIMEOUT"
            if isinstance(last_error, asyncio.TimeoutError)
            else "TOOL_EXECUTION_FAILED"
        )
        return self._error(
            error_code,
            (
                "Tool execution timed out."
                if error_code == "TOOL_TIMEOUT"
                else "Tool execution failed."
            ),
            action.tool_name,
            attempts,
            started,
        )

    @staticmethod
    def _with_audit(
        result: dict[str, Any],
        *,
        tool_name: str,
        attempts: int,
        started: float,
    ) -> dict[str, Any]:
        audited = dict(result)
        audited["_execution"] = {
            "tool_name": tool_name,
            "attempts": attempts,
            "latency_ms": round((perf_counter() - started) * 1000, 3),
        }
        logger.info("tool_execution=%s", audited["_execution"])
        return audited

    @staticmethod
    def _error(
        code: str,
        message: str,
        tool_name: str | None = None,
        attempts: int = 0,
        started: float | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "error": code,
            "message": message,
        }
        if tool_name:
            result["_execution"] = {
                "tool_name": tool_name,
                "attempts": attempts,
                "latency_ms": round(
                    (perf_counter() - started) * 1000,
                    3,
                ) if started is not None else 0.0,
            }
        return result
