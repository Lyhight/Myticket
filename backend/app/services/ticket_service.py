import asyncio
from datetime import datetime, timezone
from uuid import uuid4
from weakref import WeakValueDictionary

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from time import perf_counter

from app.agent.customer_service_agent import CustomerServiceAgent
from app.agent.schemas import (
    AgentAction,
    ClassificationExecution,
    CustomerServiceAgentResult,
    TicketClassification,
)
from app.agent.state import AgentState
from app.agent.tool_context import ToolExecutionContext
from app.models.user import User
from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_memory_repository import UserMemoryRepository
from app.agent.memory.long_term import LongTermMemoryService
from app.kb.retrieval import HybridKnowledgeRetriever
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.agent_task_repository import AgentTaskRepository
from app.repositories.user_repository import UserRepository
from app.schemas.ticket import TicketCreate
from app.agent.trace import build_memory_trace, build_rag_trace
from app.agent.guardrails import InputGuard
from app.core.config import settings
from app.graph.runtime import LangGraphCustomerServiceRuntime
from app.services.feedback_service import FeedbackService


# 单进程内，同一个工单只允许一条消息进入 Agent；不同工单仍可并行。
_ticket_message_locks: WeakValueDictionary[int, asyncio.Lock] = (
    WeakValueDictionary()
)


def _ticket_lock(ticket_id: int) -> asyncio.Lock:
    lock = _ticket_message_locks.get(ticket_id)
    if lock is None:
        lock = asyncio.Lock()
        _ticket_message_locks[ticket_id] = lock
    return lock


def _should_escalate(result: CustomerServiceAgentResult) -> bool:
    """
    判断本轮 Agent 结果是否应该转人工。

    触发条件（任一）：
    1. 分类优先级为 URGENT
    2. 决策动作是 escalate_to_human（AI 主动判断）
    3. 复核拒绝（安全兜底）
    """

    classification = result.classification_execution.classification

    if classification.priority == "URGENT":
        return True

    if result.action.action == "escalate_to_human":
        return True

    if result.review is not None and not result.review.approved:
        return True

    return False


def _escalation_status(
    result: CustomerServiceAgentResult,
    state: AgentState,
) -> str | None:
    if not _should_escalate(result):
        return None
    if (
        state.pending_action is not None
        or (result.review is not None and not result.review.approved)
    ):
        return "PENDING_REVIEW"
    return "WAITING_HUMAN"


class TicketService:

    def __init__(
        self,
        db: AsyncSession,
    ):
        self.db = db
        self.repo = TicketRepository(db)

        self.message_repo = MessageRepository(db)

        self.agent_run_repo = AgentRunRepository(db)
        self.task_repo = AgentTaskRepository(db)
        self.user_repo = UserRepository(db)

        self.long_term_memory = LongTermMemoryService(
            UserMemoryRepository(db)
        )
        self.knowledge_retriever = HybridKnowledgeRetriever(
            KnowledgeRepository(db)
        )

        self.agent = CustomerServiceAgent()
        self.runtime = LangGraphCustomerServiceRuntime(self.agent)

    @staticmethod
    def _can_access_ticket(current_user: User, ticket) -> bool:
        if ticket.user_id == current_user.id:
            return True
        if current_user.role in {"supervisor", "admin"}:
            return True
        return (
            current_user.role == "agent"
            and (
                ticket.assigned_agent_id == current_user.id
                or ticket.status == "WAITING_HUMAN"
            )
        )

    async def create_ticket(
        self,
        current_user: User,
        data: TicketCreate,
    ):
        """
        创建工单完整流程：

        1. 保存 Ticket
        2. 保存用户第一条 Message
        3. 调用 CustomerServiceAgent
        4. 保存 Agent 分类结果
        5. 保存 Agent 最终回复
        6. 保存 Agent 执行轨迹
        7. 返回 Ticket
        """

        workflow_started = perf_counter()

        # ---------------------------------
        # STEP 1
        # 创建 Ticket + CUSTOMER Message
        # ---------------------------------

        ticket = await self.repo.create(
            user_id=current_user.id,
            title=data.title,
            content=data.content,
        )

        # ---------------------------------
        # STEP 2
        # 调用统一 CustomerServiceAgent
        #
        # 新工单没有历史消息，
        # 所以 history=[]
        # ---------------------------------

        memory_started = perf_counter()
        long_term_memories = await self.long_term_memory.recall(
            current_user.id
        )
        memory_latency_ms = (perf_counter() - memory_started) * 1000
        rag_query = f"{data.title} {data.content}"
        rag_started = perf_counter()
        input_guard_issues = InputGuard.issues(rag_query)
        retrieved_knowledge = (
            []
            if input_guard_issues
            else await self.knowledge_retriever.retrieve(
                rag_query,
                top_k=settings.rag_top_k,
            )
        )
        rag_latency_ms = (perf_counter() - rag_started) * 1000
        agent_execution = await self.runtime.run_with_state(
            title=data.title,
            content=data.content,
            history=[],
            user_id=current_user.id,
            ticket_id=ticket.id,
            long_term_memories=long_term_memories,
            retrieved_knowledge=retrieved_knowledge,
        )
        agent_result = agent_execution.result

        # ---------------------------------
        # STEP 3
        # 取出分类结果
        # ---------------------------------

        execution = (
            agent_result.classification_execution
        )

        classification = (
            execution.classification
        )

        # ---------------------------------
        # STEP 4
        # 保存分类结果 + 分类运行信息
        # ---------------------------------

        ticket = await self.repo.update_classification(
            ticket=ticket,

            category=classification.category,

            priority=classification.priority,

            intent=classification.intent,

            route_to=classification.route_to,

            source=execution.source,

            attempts=execution.attempts,

            latency_ms=execution.latency_ms,

            fallback_used=execution.fallback_used,
        )

        # ---------------------------------
        # STEP 5
        # 保存 AI 回复
        #
        # 转人工的工单：回复先作为草稿保留在
        # AgentRun.final_reply 中，不发给客户，
        # 等人工 approve 后再生成正式消息。
        # ---------------------------------

        escalation_status = _escalation_status(
            agent_result, agent_execution.state
        )

        if escalation_status is None:
            await self.message_repo.create(
                ticket_id=ticket.id,
                sender_type="AI",
                content=agent_result.reply,
            )

        # ---------------------------------
        # STEP 6
        # 保存 Agent 执行轨迹
        # ---------------------------------

        agent_run = await self.agent_run_repo.create(
            ticket_id=ticket.id,
            result=agent_result,
            state=agent_execution.state,
            rag_trace=build_rag_trace(
                query=rag_query,
                results=retrieved_knowledge,
                latency_ms=rag_latency_ms,
            ),
            memory_trace=build_memory_trace(
                state=agent_execution.state,
                previous_state=None,
                recall_latency_ms=memory_latency_ms,
            ),
            context_trace=dict(agent_execution.state.context_metadata),
            total_latency_ms=(perf_counter() - workflow_started) * 1000,
        )
        await FeedbackService(self.db).capture_agent_failure(
            ticket_id=ticket.id,
            run=agent_run,
            question=data.content,
            result=agent_result,
            state=agent_execution.state,
            retrieved_knowledge=retrieved_knowledge,
        )
        await self.long_term_memory.remember_from_message(
            user_id=current_user.id,
            ticket_id=ticket.id,
            content=data.content,
        )

        # ---------------------------------
        # STEP 7
        # 需要转人工 -> 标记待审批
        # ---------------------------------

        if escalation_status is not None:
            ticket = await self.repo.set_status(
                ticket,
                escalation_status,
                event_type=(
                    "approval.requested"
                    if escalation_status == "PENDING_REVIEW"
                    else "ticket.escalated"
                ),
                event_payload={
                    "ticket_id": ticket.id,
                    "title": ticket.title,
                    "priority": ticket.priority,
                    "reason": agent_result.action.reason,
                    "status": escalation_status,
                },
                audience_role=(
                    "supervisor"
                    if escalation_status == "PENDING_REVIEW"
                    else "agent"
                ),
                escalation_reason=agent_result.action.reason,
            )

        # ---------------------------------
        # STEP 8
        # 返回 Ticket
        # ---------------------------------

        return ticket

    async def list_tickets(
        self,
        current_user: User,
    ):
        """
        查询当前用户的全部工单。
        """

        return await self.repo.list_by_user(
            current_user.id
        )

    async def get_ticket(
        self,
        current_user: User,
        ticket_id: int,
    ):
        """
        查询某个工单详情。
        """

        ticket = await self.repo.get_by_id(
            ticket_id
        )

        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ticket not found",
            )

        if not self._can_access_ticket(current_user, ticket):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Not allowed to access "
                    "this ticket"
                ),
            )

        return ticket

    async def delete_ticket(
        self,
        current_user: User,
        ticket_id: int,
    ) -> None:
        """删除当前用户自己的工单及其关联对话。"""
        ticket = await self.repo.get_by_id(ticket_id)

        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ticket not found",
            )

        if ticket.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to delete this ticket",
            )

        await self.repo.delete(ticket)

    async def list_agent_runs(
        self,
        current_user: User,
        ticket_id: int,
    ):
        """
        查询某个工单的 Agent 执行轨迹。

        只有工单所属用户才能查看。
        """

        # ---------------------------------
        # STEP 1
        # 查询 Ticket
        # ---------------------------------

        ticket = await self.repo.get_by_id(
            ticket_id
        )

        # ---------------------------------
        # STEP 2
        # Ticket 是否存在
        # ---------------------------------

        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ticket not found",
            )

        # ---------------------------------
        # STEP 3
        # 权限检查
        # ---------------------------------

        if not self._can_access_ticket(current_user, ticket):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Not allowed to access "
                    "this ticket"
                ),
            )

        # ---------------------------------
        # STEP 4
        # 查询 Agent 执行记录
        # ---------------------------------

        return await self.agent_run_repo.list_by_ticket(
            ticket_id
        )

    async def send_message(
        self,
        current_user: User,
        ticket_id: int,
        content: str,
        idempotency_key: str | None = None,
    ):
        ticket = await self.get_ticket(current_user, ticket_id)
        if ticket.status in {
            "PENDING_REVIEW", "WAITING_HUMAN", "HUMAN_PROCESSING"
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ticket is handled outside the Agent message flow",
            )
        task_key = (
            f"user:{current_user.id}:"
            f"{idempotency_key or uuid4().hex}"
        )
        task = await self.task_repo.create_or_get(
            key=task_key,
            ticket_id=ticket_id,
            user_id=current_user.id,
            content=content,
        )
        if (
            task.ticket_id != ticket_id
            or task.user_id != current_user.id
            or task.payload.get("content") != content
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key was already used for another request",
            )
        if task.status == "SUCCEEDED":
            return (
                await self.message_repo.get_by_id(task.result_message_id)
                if task.result_message_id else None
            )
        if task.status == "RUNNING":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Agent task is already running",
            )
        if (
            task.status == "FAILED"
            and task.next_retry_at is not None
            and task.next_retry_at
            > datetime.now(timezone.utc).replace(tzinfo=None)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Agent task is waiting for its retry window",
            )
        if task.status == "DEAD":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Agent task exhausted its retry budget",
            )

        lock = _ticket_lock(ticket_id)
        async with lock:
            await self.task_repo.mark_running(task)
            try:
                message = await self._send_message_locked(
                    current_user=current_user,
                    ticket_id=ticket_id,
                    content=content,
                    operation_key=f"agent-task:{task.id}",
                )
            except Exception as exc:
                await self.task_repo.mark_failed(task, str(exc))
                raise
            await self.task_repo.mark_succeeded(
                task,
                message.id if message else None,
            )
            return message

    async def list_failed_tasks(self):
        return await self.task_repo.list_failed()

    async def get_task(
        self,
        *,
        current_user: User,
        ticket_id: int,
        task_id: int,
    ):
        task = await self.task_repo.get_by_id(task_id)
        if task is None or task.ticket_id != ticket_id:
            raise HTTPException(status_code=404, detail="Agent task not found")
        if task.user_id != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Not allowed to access this task")
        return task

    async def enqueue_message(
        self,
        *,
        current_user: User,
        ticket_id: int,
        content: str,
        idempotency_key: str | None = None,
    ):
        ticket = await self.get_ticket(current_user, ticket_id)
        if ticket.status in {
            "PENDING_REVIEW", "WAITING_HUMAN", "HUMAN_PROCESSING"
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ticket is handled outside the Agent message flow",
            )
        key = f"user:{current_user.id}:{idempotency_key or uuid4().hex}"
        task = await self.task_repo.create_or_get(
            key=key,
            ticket_id=ticket_id,
            user_id=current_user.id,
            content=content,
        )
        if (
            task.ticket_id != ticket_id
            or task.user_id != current_user.id
            or task.payload.get("content") != content
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key was already used for another request",
            )
        return task

    async def execute_claimed_task(
        self,
        *,
        task_id: int,
        worker_id: str,
        attempt: int,
    ):
        task = await self.task_repo.get_by_id(task_id)
        if (
            task is None
            or task.status != "RUNNING"
            or task.locked_by != worker_id
            or task.attempts != attempt
        ):
            raise RuntimeError("Worker does not own this task lease")
        user = await self.user_repo.get_by_id(task.user_id)
        if user is None:
            await self.task_repo.fail_claimed(
                task_id=task.id,
                worker_id=worker_id,
                attempt=attempt,
                max_attempts=task.max_attempts,
                error="Task user no longer exists",
            )
            raise RuntimeError("Task user no longer exists")
        lock = _ticket_lock(task.ticket_id)
        async with lock:
            try:
                message = await self._send_message_locked(
                    current_user=user,
                    ticket_id=task.ticket_id,
                    content=str(task.payload["content"]),
                    operation_key=f"agent-task:{task.id}",
                )
            except Exception as exc:
                await self.task_repo.fail_claimed(
                    task_id=task.id,
                    worker_id=worker_id,
                    attempt=attempt,
                    max_attempts=task.max_attempts,
                    error=str(exc),
                )
                raise
            completed = await self.task_repo.complete_claimed(
                task_id=task.id,
                worker_id=worker_id,
                attempt=attempt,
                message_id=message.id if message else None,
            )
            if not completed:
                raise RuntimeError("Task lease was lost before completion")
            return message

    async def retry_task(self, task_id: int):
        task = await self.task_repo.get_by_id(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Agent task not found")
        if task.status != "FAILED":
            raise HTTPException(status_code=409, detail="Only failed tasks can be retried")
        user = await self.user_repo.get_by_id(task.user_id)
        if user is None:
            raise HTTPException(status_code=409, detail="Task user no longer exists")
        await self.task_repo.allow_manual_retry(task)
        return await self.send_message(
            current_user=user,
            ticket_id=task.ticket_id,
            content=str(task.payload["content"]),
            idempotency_key=task.idempotency_key.split(":", 2)[-1],
        )

    async def _send_message_locked(
        self,
        current_user: User,
        ticket_id: int,
        content: str,
        operation_key: str | None = None,
    ):
        """
        向已有工单继续发送消息。

        这是多轮对话的核心流程：

        1. 查询 Ticket
        2. 检查权限
        3. 读取历史 Message
        4. 构造 Agent history
        5. 保存用户最新 Message
        6. 调用 CustomerServiceAgent
        7. 保存 AI 回复
        8. 保存 Agent 执行轨迹
        9. 返回 AI Message
        """

        workflow_started = perf_counter()

        if operation_key:
            existing_reply = await self.message_repo.get_by_operation_key(
                f"{operation_key}:assistant"
            )
            if existing_reply is not None:
                return existing_reply

        # ---------------------------------
        # STEP 1
        # 查询 Ticket
        # ---------------------------------

        ticket = await self.repo.get_by_id(
            ticket_id
        )

        # ---------------------------------
        # STEP 2
        # Ticket 是否存在
        # ---------------------------------

        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ticket not found",
            )

        # ---------------------------------
        # STEP 3
        # 权限检查
        # ---------------------------------

        if ticket.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Not allowed to access "
                    "this ticket"
                ),
            )

        if ticket.status == "PENDING_REVIEW":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ticket is pending human review",
            )

        # 数据库层乐观锁：即使部署了多个 API 进程，也只有一个请求
        # 能从当前版本继续，避免重复执行退款等有副作用的工具。
        claimed = await self.repo.claim_version(
            ticket=ticket,
            expected_version=ticket.version,
        )
        if not claimed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Ticket state changed while processing; "
                    "please retry the message"
                ),
            )

        if ticket.status == "RESOLVED":
            ticket = await self.repo.set_status(ticket, "OPEN")

        # ---------------------------------
        # STEP 4
        # 读取旧的历史消息
        #
        # 注意：
        # 这里要在保存当前新消息之前查询。
        #
        # 因为当前 content 会单独作为
        # 最新消息传给 Agent。
        #
        # 如果先保存再查历史，
        # 当前消息就会出现两次。
        # ---------------------------------

        old_messages = (
            await self.message_repo.list_by_ticket(
                ticket_id
            )
        )

        # ---------------------------------
        # STEP 5
        # 转换为 Agent 可用 history
        # ---------------------------------

        history: list[dict[str, str]] = []

        for message in old_messages:

            if (
                operation_key
                and message.operation_key
                == f"{operation_key}:customer"
            ):
                continue

            if message.sender_type == "CUSTOMER":
                role = "user"

            elif message.sender_type in ("AI", "AGENT"):
                role = "assistant"

            else:
                role = "unknown"

            history.append(
                {
                    "role": role,
                    "content": message.content,
                }
            )

        # ---------------------------------
        # STEP 6
        # 保存用户当前的新消息
        # ---------------------------------

        await self.message_repo.create(
            ticket_id=ticket_id,
            sender_type="CUSTOMER",
            content=content,
            operation_key=(
                f"{operation_key}:customer"
                if operation_key else None
            ),
        )

        # ---------------------------------
        # STEP 7
        # 调用 Agent
        #
        # Agent 此时同时看到：
        #
        # history
        # +
        # 当前最新 content
        # ---------------------------------

        previous_state = (
            await self.agent_run_repo.get_latest_state_by_ticket(
                ticket_id
            )
        )
        memory_started = perf_counter()
        long_term_memories = await self.long_term_memory.recall(
            current_user.id
        )
        memory_latency_ms = (perf_counter() - memory_started) * 1000
        rag_query = f"{ticket.title} {content}"
        rag_started = perf_counter()
        input_guard_issues = InputGuard.issues(rag_query)
        retrieved_knowledge = (
            []
            if input_guard_issues
            else await self.knowledge_retriever.retrieve(
                rag_query,
                top_k=settings.rag_top_k,
            )
        )
        rag_latency_ms = (perf_counter() - rag_started) * 1000

        if (
            previous_state is not None
            and previous_state.current_step
            == "waiting_for_confirmation"
            and previous_state.category == "REFUND"
        ):
            agent_execution = await self.runtime.resume_from_state(
                previous_state=previous_state,
                content=content,
                user_id=current_user.id,
                ticket_id=ticket.id,
            )
        else:
            agent_execution = await self.runtime.run_with_state(
                title=ticket.title,
                content=content,
                history=history,
                user_id=current_user.id,
                ticket_id=ticket.id,
                previous_state=previous_state,
                long_term_memories=long_term_memories,
                retrieved_knowledge=retrieved_knowledge,
            )
        agent_result = agent_execution.result

        # ---------------------------------
        # STEP 8
        # 保存 AI 回复
        #
        # 转人工的工单不直接回复，
        # 草稿保留在 AgentRun.final_reply 中。
        # ---------------------------------

        escalation_status = _escalation_status(
            agent_result, agent_execution.state
        )

        ai_message = None

        if escalation_status is None:
            ai_message = await self.message_repo.create(
                ticket_id=ticket_id,
                sender_type="AI",
                content=agent_result.reply,
                operation_key=(
                    f"{operation_key}:assistant"
                    if operation_key else None
                ),
            )

        # ---------------------------------
        # STEP 9
        # 保存本轮 Agent Trace
        # ---------------------------------

        agent_run = await self.agent_run_repo.create(
            ticket_id=ticket_id,
            result=agent_result,
            state=agent_execution.state,
            rag_trace=build_rag_trace(
                query=rag_query,
                results=retrieved_knowledge,
                latency_ms=rag_latency_ms,
            ),
            memory_trace=build_memory_trace(
                state=agent_execution.state,
                previous_state=previous_state,
                recall_latency_ms=memory_latency_ms,
            ),
            context_trace=dict(agent_execution.state.context_metadata),
            total_latency_ms=(perf_counter() - workflow_started) * 1000,
        )
        await FeedbackService(self.db).capture_agent_failure(
            ticket_id=ticket_id,
            run=agent_run,
            question=content,
            result=agent_result,
            state=agent_execution.state,
            retrieved_knowledge=retrieved_knowledge,
        )
        await self.long_term_memory.remember_from_message(
            user_id=current_user.id,
            ticket_id=ticket_id,
            content=content,
        )

        # ---------------------------------
        # STEP 10
        # 需要转人工 -> 标记待审批
        # ---------------------------------

        if escalation_status is not None:
            await self.repo.set_status(
                ticket,
                escalation_status,
                event_type=(
                    "approval.requested"
                    if escalation_status == "PENDING_REVIEW"
                    else "ticket.escalated"
                ),
                event_payload={
                    "ticket_id": ticket.id,
                    "title": ticket.title,
                    "priority": ticket.priority,
                    "reason": agent_result.action.reason,
                    "status": escalation_status,
                },
                audience_role=(
                    "supervisor"
                    if escalation_status == "PENDING_REVIEW"
                    else "agent"
                ),
                escalation_reason=agent_result.action.reason,
            )

        # ---------------------------------
        # STEP 11
        # 返回 AI Message
        #
        # 转人工时没有 AI 回复，返回 None。
        # ---------------------------------

        return ai_message

    async def list_pending_tickets(
        self,
    ):
        """
        查询所有待人工审批的工单（管理员）。
        """

        return await self.repo.list_pending()

    async def list_handoff_queue(self):
        return await self.repo.list_handoff_queue()

    async def list_assigned_tickets(self, agent: User):
        return await self.repo.list_assigned(agent.id)

    async def claim_handoff(self, agent: User, ticket_id: int):
        ticket = await self.repo.claim_for_agent(ticket_id, agent.id)
        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ticket was already claimed or is not waiting",
            )
        return ticket

    async def send_human_message(
        self,
        current_user: User,
        ticket_id: int,
        content: str,
    ):
        ticket = await self.repo.get_by_id(ticket_id)
        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ticket not found",
            )
        is_customer = ticket.user_id == current_user.id
        is_assigned = ticket.assigned_agent_id == current_user.id
        is_supervisor = current_user.role in {"supervisor", "admin"}
        if not (is_customer or is_assigned or is_supervisor):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to send a human-support message",
            )
        if ticket.status not in {"WAITING_HUMAN", "HUMAN_PROCESSING"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ticket is not in human support",
            )
        sender_type = "CUSTOMER" if is_customer else "HUMAN_AGENT"
        return await self.message_repo.create(
            ticket_id=ticket_id,
            sender_type=sender_type,
            content=content,
            event_type="message.created",
            audience_role=(
                "agent"
                if is_customer and ticket.assigned_agent_id is None
                else None
            ),
            audience_user_id=(ticket.user_id if not is_customer else ticket.assigned_agent_id),
        )

    async def resolve_handoff(self, agent: User, ticket_id: int):
        ticket = await self.repo.get_by_id(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if (
            ticket.assigned_agent_id != agent.id
            and agent.role not in {"supervisor", "admin"}
        ):
            raise HTTPException(status_code=403, detail="Ticket is assigned to another agent")
        if ticket.status != "HUMAN_PROCESSING":
            raise HTTPException(status_code=409, detail="Ticket is not being handled")
        return await self.repo.set_status(
            ticket,
            "RESOLVED",
            event_type="ticket.resolved",
            event_payload={"ticket_id": ticket.id, "agent_id": agent.id},
            audience_user_id=ticket.user_id,
        )

    async def approve_ticket(
        self,
        ticket_id: int,
    ):
        lock = _ticket_lock(ticket_id)
        async with lock:
            return await self._approve_ticket_locked(ticket_id)

    async def _approve_ticket_locked(
        self,
        ticket_id: int,
    ):
        """
        人工审批通过：

        1. 校验工单处于 PENDING_REVIEW
        2. 取出最近一次 Agent 草稿回复
        3. 生成正式 AI 消息
        4. 工单标记 RESOLVED
        """

        ticket = await self.repo.get_by_id(
            ticket_id
        )

        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ticket not found",
            )

        if ticket.status != "PENDING_REVIEW":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ticket is not pending review",
            )

        claimed = await self.repo.claim_version(
            ticket=ticket,
            expected_version=ticket.version,
        )
        if not claimed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ticket state changed; reload before approval",
            )

        latest_run = (
            await self.agent_run_repo.get_latest_by_ticket(
                ticket_id
            )
        )

        latest_state = (
            await self.agent_run_repo.get_latest_state_by_ticket(
                ticket_id
            )
        )

        # 若 checkpoint 中保存了待审批动作，审批必须执行该动作，
        # 而不是只把 Agent 草稿回复发送给客户。
        if (
            latest_state is not None
            and latest_state.current_step == "waiting_for_human"
            and latest_state.pending_action is not None
        ):
            pending = latest_state.pending_action

            if pending.is_expired():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Pending action has expired",
                )

            if not pending.matches_confirmation(
                latest_state.confirmation_summary or ""
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Pending action integrity check failed",
                )

            approved_args = dict(pending.tool_args)
            approved_args["confirmed"] = True
            approved_args["human_approved"] = True
            latest_state.confirm_action(pending.tool_name)
            latest_state.current_step = "executing_tool"
            action = AgentAction(
                action="tool",
                tool_name=pending.tool_name,
                tool_args=approved_args,
                reason="human_approved_pending_action",
            )
            tool_result = await self.agent.tool_executor.execute(
                action,
                context=ToolExecutionContext(
                    user_id=ticket.user_id,
                    ticket_id=ticket_id,
                    human_approved=True,
                ),
                state=latest_state,
            )
            latest_state.record_tool_execution(
                tool_name=pending.tool_name,
                arguments=approved_args,
                result=tool_result,
            )

            if not tool_result or not tool_result.get("success"):
                latest_state.current_step = "waiting_for_human"
                latest_state.errors.append(
                    "human_approved_action_failed"
                )
                reply_content = (
                    "人工审批后的操作执行失败，请继续人工处理。"
                )
            else:
                latest_state.pending_action = None
                latest_state.requires_confirmation = False
                latest_state.current_step = "completed"
                refund = tool_result.get("refund", {})
                request_no = refund.get("request_no")
                reply_content = (
                    f"退款申请{request_no}已通过人工审核并创建，"
                    "请等待处理。"
                )

            latest_state.action = action
            latest_state.reply = reply_content
            classification = TicketClassification(
                category=latest_state.category or "REFUND",
                priority=latest_state.priority or "HIGH",
                intent=(
                    latest_state.intent or "refund_or_return"
                ),
                route_to=(
                    latest_state.route_to or "after_sales"
                ),
            )
            result = CustomerServiceAgentResult(
                classification_execution=ClassificationExecution(
                    classification=classification,
                    source="checkpoint",
                    fallback_used=False,
                    attempts=0,
                    latency_ms=0,
                ),
                action=action,
                tool_result=tool_result,
                reply=reply_content,
            )
            await self.agent_run_repo.create(
                ticket_id=ticket_id,
                result=result,
                state=latest_state,
            )

            if not tool_result or not tool_result.get("success"):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Approved action execution failed",
                )

        elif latest_run is not None and latest_run.final_reply:
            reply_content = latest_run.final_reply
        else:
            reply_content = (
                "您好，您的问题已由人工客服处理完成，"
                "感谢您的耐心等待。"
            )

        await self.message_repo.create(
            ticket_id=ticket_id,
            sender_type="AI",
            content=reply_content,
            event_type="message.created",
            audience_user_id=ticket.user_id,
        )

        return await self.repo.set_status(
            ticket,
            "RESOLVED",
            event_type="ticket.resolved",
            event_payload={"ticket_id": ticket.id, "source": "approval"},
            audience_user_id=ticket.user_id,
        )

    async def reject_ticket(
        self,
        ticket_id: int,
        content: str | None,
    ):
        lock = _ticket_lock(ticket_id)
        async with lock:
            return await self._reject_ticket_locked(ticket_id, content)

    async def _reject_ticket_locked(
        self,
        ticket_id: int,
        content: str | None,
    ):
        """
        人工审批驳回：

        1. 校验工单处于 PENDING_REVIEW
        2. 若提供人工回复，生成 AGENT 消息
        3. 工单标记 RESOLVED
        """

        ticket = await self.repo.get_by_id(
            ticket_id
        )

        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ticket not found",
            )

        if ticket.status != "PENDING_REVIEW":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ticket is not pending review",
            )

        claimed = await self.repo.claim_version(
            ticket=ticket,
            expected_version=ticket.version,
        )
        if not claimed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ticket state changed; reload before rejection",
            )

        if content:
            await self.message_repo.create(
                ticket_id=ticket_id,
                sender_type="HUMAN_AGENT",
                content=content,
                event_type="message.created",
                audience_user_id=ticket.user_id,
            )

        return await self.repo.set_status(
            ticket,
            "WAITING_HUMAN",
            event_type="ticket.escalated",
            event_payload={
                "ticket_id": ticket.id,
                "reason": "Supervisor rejected the Agent proposal",
                "status": "WAITING_HUMAN",
            },
            audience_role="agent",
            audience_user_id=ticket.user_id,
            escalation_reason="Supervisor rejected the Agent proposal",
        )
