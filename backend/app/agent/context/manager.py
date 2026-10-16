from app.agent.context.schemas import (
    ContextBundle,
    SelectedMessage,
)
from app.agent.memory.short_term import ShortTermMemory
from app.agent.memory.summarizer import RollingConversationSummarizer
from app.agent.state import AgentState
from app.core.config import settings


class ContextManager:
    """在固定预算内选择当前决策真正需要的上下文。"""

    def __init__(
        self,
        *,
        max_history_characters: int | None = None,
        max_messages: int | None = None,
        max_tool_results: int | None = None,
        max_context_characters: int | None = None,
        max_memory_characters: int | None = None,
        max_knowledge_characters: int | None = None,
        summarizer: RollingConversationSummarizer | None = None,
    ) -> None:
        self.max_history_characters = (
            max_history_characters
            if max_history_characters is not None
            else settings.context_max_history_characters
        )
        self.max_messages = (
            max_messages if max_messages is not None else settings.context_max_messages
        )
        self.max_tool_results = (
            max_tool_results
            if max_tool_results is not None
            else settings.context_max_tool_results
        )
        self.max_context_characters = (
            max_context_characters
            if max_context_characters is not None
            else settings.context_max_characters
        )
        self.max_memory_characters = (
            max_memory_characters
            if max_memory_characters is not None
            else settings.context_max_memory_characters
        )
        self.max_knowledge_characters = (
            max_knowledge_characters
            if max_knowledge_characters is not None
            else settings.context_max_knowledge_characters
        )
        self.summarizer = summarizer or RollingConversationSummarizer()

    def build(self, state: AgentState) -> ContextBundle:
        selected_reversed: list[SelectedMessage] = []
        used_characters = 0

        for turn in reversed(state.history):
            if len(selected_reversed) >= self.max_messages:
                break

            content_length = len(turn.content)
            if (
                selected_reversed
                and used_characters + content_length
                > self.max_history_characters
            ):
                break

            selected_reversed.append(
                SelectedMessage(
                    role=turn.role,
                    content=turn.content,
                )
            )
            used_characters += content_length

        selected = list(reversed(selected_reversed))
        omitted_count = len(state.history) - len(selected)
        previous_summarized_count = int(
            state.context_metadata.get(
                "summarized_message_count",
                0,
            )
        )
        first_unsummarized = min(
            previous_summarized_count,
            omitted_count,
        )
        conversation_summary = self.summarizer.summarize(
            previous_summary=state.conversation_summary,
            omitted_messages=(
                state.history[first_unsummarized:omitted_count]
                if omitted_count > first_unsummarized
                else []
            ),
        )
        selected_memories, memory_used = self._select_items(
            state.long_term_memories,
            self.max_memory_characters,
        )
        selected_knowledge, knowledge_used = self._select_items(
            state.retrieved_knowledge,
            self.max_knowledge_characters,
        )
        working_memory = ShortTermMemory(
            conversation_summary=conversation_summary,
            active_goal=(
                state.intent
                or state.action.reason
                if state.action
                else state.intent
            ),
            known_facts=dict(state.entities),
            missing_information=list(state.missing_fields),
            important_tool_results=[
                record.model_dump(mode="json")
                for record in state.tool_history[
                    -self.max_tool_results:
                ]
            ],
            long_term_memories=selected_memories,
            retrieved_knowledge=selected_knowledge,
        )
        memory_characters = len(
            str(working_memory.model_dump(mode="json"))
        )
        estimated_tokens = max(
            1,
            (used_characters + memory_characters) // 2,
        )
        used_total = used_characters + memory_characters

        # 最终硬预算：优先保留结构化状态、记忆和 RAG，超出时继续
        # 从最旧的对话消息开头裁剪。
        while selected and used_total > self.max_context_characters:
            removed = selected.pop(0)
            used_characters -= len(removed.content)
            used_total = used_characters + memory_characters
        estimated_tokens = max(1, used_total // 2)

        sources = ["agent_state", "recent_messages"]
        if state.tool_history:
            sources.append("tool_history")
        if conversation_summary:
            sources.append("conversation_summary")
        if state.long_term_memories:
            sources.append("long_term_memory")
        if state.retrieved_knowledge:
            sources.append("knowledge_base")

        return ContextBundle(
            messages=selected,
            working_memory=working_memory,
            estimated_tokens=estimated_tokens,
            original_message_count=len(state.history),
            selected_message_count=len(selected),
            summarized_message_count=max(
                previous_summarized_count,
                omitted_count,
            ),
            truncated=len(selected) < len(state.history),
            sources=sources,
            budget_characters=self.max_context_characters,
            used_characters=used_total,
            dropped_memory_count=(
                len(state.long_term_memories) - len(selected_memories)
            ),
            dropped_knowledge_count=(
                len(state.retrieved_knowledge) - len(selected_knowledge)
            ),
        )

    @staticmethod
    def _select_items(
        items: list[dict],
        character_budget: int,
    ) -> tuple[list[dict], int]:
        selected: list[dict] = []
        used = 0
        for item in items:
            size = len(str(item))
            if selected and used + size > character_budget:
                break
            if size > character_budget:
                continue
            selected.append(dict(item))
            used += size
        return selected, used
