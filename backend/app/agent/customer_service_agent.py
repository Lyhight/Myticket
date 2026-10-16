import logging
from datetime import datetime, timedelta, timezone

from app.agent.decision import QwenDecisionAgent
from app.agent.context.manager import ContextManager
from app.agent.memory.restorer import ShortTermMemoryRestorer
from app.agent.entity_extractor import (
    RuleBasedEntityExtractor,
)
from app.agent.reply_service import AutoReplyService
from app.agent.workflows.refund import RefundWorkflow
from app.agent.retry import run_with_retry
from app.agent.review_service import ReplyReviewService
from app.agent.schemas import (
    AgentAction,
    ClassificationExecution,
    CustomerServiceAgentResult,
    ReviewResult,
    TicketClassification,
)
from app.agent.service import TicketClassificationService
from app.agent.state import (
    AgentExecution,
    AgentState,
    ConversationTurn,
    PendingAction,
)
from app.agent.tool_executor import ToolExecutor
from app.agent.tool_context import ToolExecutionContext
from app.agent.guardrails import InputGuard
from app.core.config import settings


logger = logging.getLogger(__name__)

SAFE_REPLY_AFTER_REJECT = (
    "您好，您的问题我们已经收到并记录。"
    "由于需要进一步核实，已为您转交人工处理，"
    "请您稍后留意，感谢理解。"
)


class CustomerServiceAgent:

    def __init__(self):

        self.classifier = TicketClassificationService()

        self.decision_agent = (
            QwenDecisionAgent() if settings.llm_enabled else None
        )

        self.entity_extractor = RuleBasedEntityExtractor()

        self.context_manager = ContextManager()

        self.memory_restorer = ShortTermMemoryRestorer()

        self.tool_executor = ToolExecutor()

        self.refund_workflow = RefundWorkflow(
            self.tool_executor
        )

        self.reply_service = AutoReplyService()

        self.review_service = ReplyReviewService()

    async def _finish_early_reply(
        self,
        *,
        state: AgentState,
        execution: ClassificationExecution,
        action: AgentAction,
        reply: str,
        approved_step: str,
        tool_result: dict | None = None,
    ) -> AgentExecution:
        """Apply the same output review to every user-visible branch."""
        state.current_step = "reviewing"
        review = await self.review_service.review(
            reply=reply,
            title=state.title,
            content=state.user_message,
            category=state.category or "OTHER",
            intent=state.intent or "general_question",
            tool_result=tool_result,
        )
        if review.approved:
            state.current_step = approved_step
        else:
            logger.warning("Early reply rejected by review: %s", review.issues)
            reply = SAFE_REPLY_AFTER_REJECT
            state.current_step = "waiting_for_human"
            state.requires_confirmation = False
            state.pending_action = None
        state.reply = reply
        state.review = review
        return AgentExecution(
            state=state,
            result=CustomerServiceAgentResult(
                classification_execution=execution,
                action=action,
                tool_result=tool_result,
                reply=reply,
                review=review,
            ),
        )

    async def _decide_or_fallback(
        self,
        title: str,
        content: str,
        category: str,
        intent: str,
        history: list[dict[str, str]] | None,
        entities: dict[str, str] | None = None,
    ) -> AgentAction:
        """
        决策兜底：

        Qwen 决策失败（超时 / 空返回 / JSON 解析失败）
        时，降级为 direct_reply，避免整个建单 / 回复流程 500。

        绝不降级为 tool 动作，因为规则兜底无法可靠提取
        订单号 / 物流单号，编造参数比不回答更危险。
        """

        if self.decision_agent is None:
            values = entities or {}
            if category == "ORDER":
                order_id = values.get("order_id")
                return AgentAction(
                    action="tool" if order_id else "ask_user",
                    tool_name="get_order" if order_id else None,
                    tool_args={"order_id": order_id} if order_id else {},
                    reason="offline_rule_decision",
                    message=None if order_id else "请提供需要查询的订单号。",
                )
            if category == "LOGISTICS":
                tracking_number = values.get("tracking_number")
                return AgentAction(
                    action="tool" if tracking_number else "ask_user",
                    tool_name="get_logistics" if tracking_number else None,
                    tool_args=(
                        {"tracking_number": tracking_number}
                        if tracking_number else {}
                    ),
                    reason="offline_rule_decision",
                    message=(
                        None
                        if tracking_number
                        else "请提供需要查询的物流单号。"
                    ),
                )
            return AgentAction(
                action="direct_reply",
                reason="offline_rule_decision",
            )

        try:
            return await run_with_retry(
                lambda: self.decision_agent.decide(
                    title=title,
                    content=content,
                    category=category,
                    intent=intent,
                    history=history,
                ),
                timeout_seconds=settings.decision_timeout_seconds,
                max_retries=settings.decision_max_retries,
                retry_delay_seconds=settings.llm_retry_delay_seconds,
            )

        except Exception:
            logger.exception(
                "Qwen decision failed, "
                "falling back to direct_reply"
            )

            return AgentAction(
                action="direct_reply",
                tool_name=None,
                tool_args={},
                reason="decision_agent_fallback",
                message=None,
            )

    async def run(
        self,
        title: str,
        content: str,
        history: list[dict[str, str]] | None = None,
        user_id: int | None = None,
        ticket_id: int | None = None,
    ) -> CustomerServiceAgentResult:

        execution = await self.run_with_state(
            title=title,
            content=content,
            history=history,
            user_id=user_id,
            ticket_id=ticket_id,
        )

        return execution.result

    async def run_with_state(
        self,
        title: str,
        content: str,
        history: list[dict[str, str]] | None = None,
        ticket_id: int | None = None,
        user_id: int | None = None,
        previous_state: AgentState | None = None,
        long_term_memories: list[dict] | None = None,
        retrieved_knowledge: list[dict] | None = None,
    ) -> AgentExecution:
        """执行客服 Agent，并返回可追踪、可持久化的状态。"""

        conversation_history: list[ConversationTurn] = []
        rejected_history_messages = 0

        for item in history or []:
            role = item.get("role", "system")

            if role not in {"user", "assistant", "system"}:
                role = "system"

            message_content = str(item.get("content", ""))
            if InputGuard.issues(message_content):
                rejected_history_messages += 1
                continue
            conversation_history.append(
                ConversationTurn(role=role, content=message_content)
            )

        state = AgentState(
            ticket_id=ticket_id,
            title=title,
            user_message=content,
            history=conversation_history,
            current_step="classifying",
        )
        state = self.memory_restorer.restore(
            state=state,
            previous_state=previous_state,
        )
        if InputGuard.issues(state.conversation_summary or ""):
            state.conversation_summary = None
            state.context_metadata["rejected_conversation_summary"] = True
        safe_memories, rejected_memories = InputGuard.sanitize_knowledge(
            list(long_term_memories or [])
        )
        state.long_term_memories = safe_memories
        if rejected_history_messages:
            state.context_metadata["rejected_history_messages"] = (
                rejected_history_messages
            )
        if rejected_memories:
            state.context_metadata["rejected_memory_items"] = rejected_memories
        safe_knowledge, rejected_knowledge = (
            InputGuard.sanitize_knowledge(
                list(retrieved_knowledge or [])
            )
        )
        state.retrieved_knowledge = safe_knowledge
        if rejected_knowledge:
            state.context_metadata[
                "rejected_knowledge_chunks"
            ] = rejected_knowledge

        injection_issues = InputGuard.issues(f"{title}\n{content}")
        if injection_issues:
            classification = TicketClassification(
                category="OTHER",
                priority="URGENT",
                intent="prompt_injection",
                route_to="general_support",
            )
            execution = ClassificationExecution(
                classification=classification,
                source="rule_based",
                fallback_used=True,
                attempts=0,
                latency_ms=0,
            )
            state.category = classification.category
            state.priority = classification.priority
            state.intent = classification.intent
            state.route_to = classification.route_to
            action = AgentAction(
                action="escalate_to_human",
                reason="prompt_injection_detected",
                message=(
                    "该请求需要人工客服进一步核实，"
                    "已为您转交处理。"
                ),
            )
            state.action = action
            state.current_step = "waiting_for_human"
            state.errors.extend(injection_issues)
            state.reply = action.message
            review = ReviewResult(
                approved=False,
                issues=injection_issues,
            )
            state.review = review
            return AgentExecution(
                state=state,
                result=CustomerServiceAgentResult(
                    classification_execution=execution,
                    action=action,
                    tool_result=None,
                    reply=action.message,
                    review=review,
                ),
            )

        # -------------------------
        # 1. 工单分类
        # -------------------------

        execution = await self.classifier.classify(
                title=title,
                content=content,
            )

        classification = execution.classification

        state.category = classification.category
        state.priority = classification.priority
        state.intent = classification.intent
        state.route_to = classification.route_to

        state.current_step = "extracting_entities"

        safe_history = [turn.model_dump() for turn in conversation_history]

        entity_extraction = await self.entity_extractor.extract(
            title=title,
            content=content,
            history=safe_history,
        )
        state.entities.update(entity_extraction.entities)

        if (
            classification.category == "REFUND"
            and user_id is not None
        ):
            workflow_execution = await self.refund_workflow.start(
                state=state,
                execution=execution,
                context=ToolExecutionContext(
                    user_id=user_id,
                    ticket_id=ticket_id,
                ),
            )
            workflow_result = workflow_execution.result
            return await self._finish_early_reply(
                state=workflow_execution.state,
                execution=workflow_result.classification_execution,
                action=workflow_result.action,
                reply=workflow_result.reply,
                approved_step=workflow_execution.state.current_step,
                tool_result=workflow_result.tool_result,
            )

        state.current_step = "deciding"

        context_bundle = self.context_manager.build(state)
        state.conversation_summary = (
            context_bundle.working_memory.conversation_summary
        )
        guardrail_metadata = dict(state.context_metadata)
        state.context_metadata = {
            **guardrail_metadata,
            "estimated_tokens": context_bundle.estimated_tokens,
            "original_message_count": (
                context_bundle.original_message_count
            ),
            "selected_message_count": (
                context_bundle.selected_message_count
            ),
            "summarized_message_count": (
                context_bundle.summarized_message_count
            ),
            "truncated": context_bundle.truncated,
            "sources": context_bundle.sources,
            "budget_characters": context_bundle.budget_characters,
            "used_characters": context_bundle.used_characters,
            "dropped_memory_count": (
                context_bundle.dropped_memory_count
            ),
            "dropped_knowledge_count": (
                context_bundle.dropped_knowledge_count
            ),
        }
        decision_history = context_bundle.decision_history()

        # -------------------------
        # 2. Agent 决策
        # -------------------------

        action = await self._decide_or_fallback(
            title=title,
            content=content,
            category=classification.category,
            intent=classification.intent,
            history=decision_history,
            entities=state.entities,
        )

        state.action = action

        if action.action == "request_confirmation":
            reply = (
                action.message
                or "请确认是否执行该操作。"
            )

            if not action.tool_name:
                state.add_error(
                    "Confirmation action is missing tool_name"
                )
                reply = SAFE_REPLY_AFTER_REJECT

            else:
                state.current_step = (
                    "waiting_for_confirmation"
                )
                state.requires_confirmation = True
                state.confirmation_summary = reply
                state.pending_action = PendingAction(
                    tool_name=action.tool_name,
                    tool_args=dict(action.tool_args),
                    expires_at=(
                        datetime.now(timezone.utc)
                        + timedelta(minutes=10)
                    ),
                )
                state.pending_action.confirmation_hash = (
                    PendingAction.fingerprint(
                        tool_name=state.pending_action.tool_name,
                        tool_args=state.pending_action.tool_args,
                        summary=reply,
                    )
                )

            return await self._finish_early_reply(
                state=state,
                execution=execution,
                action=action,
                reply=reply,
                approved_step=state.current_step,
            )

        if action.action == "tool":
            required_fields = (
                self.entity_extractor.required_fields_for_tool(
                    action.tool_name
                )
            )

            # 模型正确选择了工具但漏传参数时，优先使用
            # 规则提取出的、可验证的实体补齐调用参数。
            for field in required_fields:
                extracted_value = state.entities.get(field)

                if (
                    not action.tool_args.get(field)
                    and extracted_value
                ):
                    action.tool_args[field] = extracted_value

            state.missing_fields = (
                self.entity_extractor.find_missing_fields(
                    tool_name=action.tool_name,
                    entities=state.entities,
                    tool_args=action.tool_args,
                )
            )

            if state.missing_fields:
                question = self.entity_extractor.question_for(
                    state.missing_fields
                )
                action = AgentAction(
                    action="ask_user",
                    reason="missing_required_tool_arguments",
                    message=question,
                )
                state.action = action
                state.current_step = "waiting_for_user"
                return await self._finish_early_reply(
                    state=state,
                    execution=execution,
                    action=action,
                    reply=question,
                    approved_step="waiting_for_user",
                )

        # -------------------------
        # 3. 缺参数 -> 主动追问
        # -------------------------

        if action.action == "ask_user":

            reply = (
                action.message
                or "请补充完成查询所需的信息。"
            )

            return await self._finish_early_reply(
                state=state,
                execution=execution,
                action=action,
                reply=reply,
                approved_step="waiting_for_user",
            )

        # -------------------------
        # 4. 转人工
        # -------------------------

        if action.action == "escalate_to_human":

            reply = (
                action.message
                or "好的，正在为您转接人工客服，请稍候。"
            )

            return await self._finish_early_reply(
                state=state,
                execution=execution,
                action=action,
                reply=reply,
                approved_step="waiting_for_human",
            )

        # -------------------------
        # 5. 执行 Tool
        # -------------------------

        if action.action == "tool":
            state.current_step = "executing_tool"

        tool_context = (
            ToolExecutionContext(
                user_id=user_id,
                ticket_id=ticket_id,
            )
            if user_id is not None
            else None
        )

        tool_result = await self.tool_executor.execute(
            action,
            context=tool_context,
            state=state,
        )

        if action.action == "tool" and action.tool_name:
            state.record_tool_execution(
                tool_name=action.tool_name,
                arguments=action.tool_args,
                result=tool_result,
            )

        # -------------------------
        # 6. 生成最终回复
        # -------------------------

        state.current_step = "generating_reply"

        reply = (
            await self.reply_service.generate(
                title=title,
                content=content,
                category=(
                    classification.category
                ),
                priority=(
                    classification.priority
                ),
                intent=(
                    classification.intent
                ),
                tool_result=tool_result,
                knowledge_context=state.retrieved_knowledge,
            )
        )

        # -------------------------
        # 7. 结果复核
        # -------------------------

        state.current_step = "reviewing"

        review = await self.review_service.review(
            reply=reply,
            title=title,
            content=content,
            category=classification.category,
            intent=classification.intent,
            tool_result=tool_result,
        )

        if not review.approved:
            logger.warning(
                "Reply rejected by review: %s",
                review.issues,
            )

            reply = SAFE_REPLY_AFTER_REJECT

            state.current_step = "waiting_for_human"

        else:
            state.current_step = "completed"

        state.reply = reply
        state.review = review

        # -------------------------
        # 8. 返回统一 Agent 结果
        # -------------------------

        result = CustomerServiceAgentResult(
            classification_execution=execution,
            action=action,
            tool_result=tool_result,
            reply=reply,
            review=review,
        )

        return AgentExecution(
            state=state,
            result=result,
        )

    async def resume_from_state(
        self,
        *,
        previous_state: AgentState,
        content: str,
        user_id: int,
        ticket_id: int,
    ) -> AgentExecution:
        if (
            previous_state.current_step
            != "waiting_for_confirmation"
            or previous_state.category != "REFUND"
        ):
            raise ValueError(
                "State is not a resumable refund checkpoint"
            )

        workflow_execution = await self.refund_workflow.resume(
            previous_state=previous_state,
            content=content,
            context=ToolExecutionContext(
                user_id=user_id,
                ticket_id=ticket_id,
            ),
        )
        workflow_result = workflow_execution.result
        return await self._finish_early_reply(
            state=workflow_execution.state,
            execution=workflow_result.classification_execution,
            action=workflow_result.action,
            reply=workflow_result.reply,
            approved_step=workflow_execution.state.current_step,
            tool_result=workflow_result.tool_result,
        )
