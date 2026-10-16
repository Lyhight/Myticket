from datetime import datetime, timedelta, timezone

from app.agent.confirmation import ConfirmationDetector
from app.agent.schemas import (
    AgentAction,
    ClassificationExecution,
    CustomerServiceAgentResult,
    TicketClassification,
)
from app.agent.state import AgentExecution, AgentState, PendingAction
from app.agent.tool_context import ToolExecutionContext
from app.agent.tool_executor import ToolExecutor


class RefundWorkflow:
    def __init__(self, tool_executor: ToolExecutor):
        self.tool_executor = tool_executor
        self.confirmation_detector = ConfirmationDetector()

    @staticmethod
    def _result(
        state: AgentState,
        execution: ClassificationExecution,
        action: AgentAction,
        reply: str,
        tool_result: dict | None = None,
    ) -> AgentExecution:
        state.action = action
        state.reply = reply
        return AgentExecution(
            state=state,
            result=CustomerServiceAgentResult(
                classification_execution=execution,
                action=action,
                tool_result=tool_result,
                reply=reply,
            ),
        )

    async def start(
        self,
        *,
        state: AgentState,
        execution: ClassificationExecution,
        context: ToolExecutionContext,
    ) -> AgentExecution:
        order_id = state.entities.get("order_id")

        if not order_id:
            state.missing_fields = ["order_id"]
            state.current_step = "waiting_for_user"
            action = AgentAction(
                action="ask_user",
                reason="refund_order_id_missing",
                message="请提供需要退款的订单号。",
            )
            return self._result(
                state, execution, action, action.message
            )

        check_action = AgentAction(
            action="tool",
            tool_name="check_refund_eligibility",
            tool_args={"order_id": order_id},
            reason="Check refund eligibility",
        )
        state.current_step = "executing_tool"
        check_result = await self.tool_executor.execute(
            check_action,
            context=context,
            state=state,
        )
        state.record_tool_execution(
            tool_name="check_refund_eligibility",
            arguments=check_action.tool_args,
            result=check_result,
        )

        if not check_result or not check_result.get("success"):
            state.current_step = "waiting_for_user"
            action = AgentAction(
                action="ask_user",
                reason="refund_order_not_found",
                message="未找到该订单，请核对订单号后重试。",
            )
            return self._result(
                state, execution, action, action.message, check_result
            )

        if check_result.get("requires_human"):
            amount = check_result.get("amount")
            summary = (
                f"订单{order_id}退款{amount}元需要人工售后审核。"
            )
            pending_action = PendingAction(
                tool_name="create_refund_request",
                tool_args={
                    "order_id": order_id,
                    "reason": state.user_message,
                    "idempotency_key": (
                        f"refund:{context.user_id}:{order_id}"
                    ),
                },
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(hours=24)
                ),
            )
            pending_action.confirmation_hash = PendingAction.fingerprint(
                tool_name=pending_action.tool_name,
                tool_args=pending_action.tool_args,
                summary=summary,
            )
            state.pending_action = pending_action
            state.confirmation_summary = summary
            state.requires_confirmation = True
            state.current_step = "waiting_for_human"
            action = AgentAction(
                action="escalate_to_human",
                reason=str(check_result.get("reason")),
                message=f"{summary} 已为您转交处理。",
            )
            return self._result(
                state, execution, action, action.message, check_result
            )

        if not check_result.get("eligible"):
            state.current_step = "completed"
            action = AgentAction(
                action="direct_reply",
                reason=str(check_result.get("reason")),
                message="该订单当前不符合退款条件。",
            )
            return self._result(
                state, execution, action, action.message, check_result
            )

        amount = check_result.get("amount")
        summary = f"订单{order_id}可申请退款{amount}元，是否确认？"
        # 用户+订单级幂等，不因用户新建另一个工单而改变。
        idempotency_key = f"refund:{context.user_id}:{order_id}"
        action = AgentAction(
            action="request_confirmation",
            tool_name="create_refund_request",
            tool_args={
                "order_id": order_id,
                "reason": state.user_message,
                "idempotency_key": idempotency_key,
            },
            reason="refund_requires_confirmation",
            message=summary,
        )
        state.action = action
        state.current_step = "waiting_for_confirmation"
        state.requires_confirmation = True
        state.confirmation_summary = summary
        pending_action = PendingAction(
            tool_name="create_refund_request",
            tool_args=dict(action.tool_args),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        pending_action.confirmation_hash = PendingAction.fingerprint(
            tool_name=pending_action.tool_name,
            tool_args=pending_action.tool_args,
            summary=summary,
        )
        state.pending_action = pending_action
        state.reply = summary
        return self._result(
            state, execution, action, summary, check_result
        )

    async def resume(
        self,
        *,
        previous_state: AgentState,
        content: str,
        context: ToolExecutionContext,
    ) -> AgentExecution:
        state = previous_state.model_copy(deep=True)
        state.user_message = content
        pending = state.pending_action
        classification = TicketClassification(
            category=state.category or "REFUND",
            priority=state.priority or "HIGH",
            intent=state.intent or "refund_or_return",
            route_to=state.route_to or "after_sales",
        )
        execution = ClassificationExecution(
            classification=classification,
            source="checkpoint",
            fallback_used=False,
            attempts=0,
            latency_ms=0,
        )

        if pending is None or pending.is_expired():
            state.requires_confirmation = False
            state.pending_action = None
            state.current_step = "completed"
            action = AgentAction(
                action="direct_reply",
                reason="confirmation_expired",
                message="本次确认已过期，请重新发起退款申请。",
            )
            return self._result(state, execution, action, action.message)

        if not pending.matches_confirmation(
            state.confirmation_summary or ""
        ):
            state.add_error("pending_action_confirmation_hash_mismatch")
            # add_error 会把步骤标成 failed；完整性失败属于需要人工接管，
            # 因此最终状态必须明确恢复为 waiting_for_human。
            state.current_step = "waiting_for_human"
            action = AgentAction(
                action="escalate_to_human",
                reason="confirmation_payload_changed",
                message="退款确认内容校验失败，已转交人工处理。",
            )
            return self._result(state, execution, action, action.message)

        intent = self.confirmation_detector.detect(content)

        if intent == "reject":
            state.requires_confirmation = False
            state.pending_action = None
            state.current_step = "completed"
            action = AgentAction(
                action="direct_reply",
                reason="user_rejected_refund",
                message="已取消本次退款操作。",
            )
            return self._result(state, execution, action, action.message)

        if intent == "unknown":
            state.current_step = "waiting_for_confirmation"
            action = AgentAction(
                action="request_confirmation",
                tool_name=pending.tool_name,
                tool_args=dict(pending.tool_args),
                reason="confirmation_unclear",
                message=(
                    f"{state.confirmation_summary}"
                    " 请明确回复“确认”或“取消”。"
                ),
            )
            return self._result(state, execution, action, action.message)

        state.confirm_action(pending.tool_name)
        state.current_step = "executing_tool"
        tool_args = dict(pending.tool_args)
        tool_args["confirmed"] = True
        action = AgentAction(
            action="tool",
            tool_name=pending.tool_name,
            tool_args=tool_args,
            reason="user_confirmed_refund",
        )
        tool_result = await self.tool_executor.execute(
            action,
            context=context,
            state=state,
        )
        state.record_tool_execution(
            tool_name=pending.tool_name,
            arguments=tool_args,
            result=tool_result,
        )
        state.pending_action = None

        if tool_result and tool_result.get("success"):
            request_no = tool_result["refund"]["request_no"]
            reply = f"退款申请{request_no}已创建，请等待处理。"
            state.current_step = "completed"
        else:
            reply = "退款申请未能自动完成，已转交人工处理。"
            state.current_step = "waiting_for_human"

        return self._result(
            state, execution, action, reply, tool_result
        )
