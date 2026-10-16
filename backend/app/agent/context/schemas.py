from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.memory.short_term import ShortTermMemory


class SelectedMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ContextBundle(BaseModel):
    messages: list[SelectedMessage] = Field(default_factory=list)
    working_memory: ShortTermMemory
    estimated_tokens: int
    original_message_count: int
    selected_message_count: int
    summarized_message_count: int
    truncated: bool
    sources: list[str] = Field(default_factory=list)
    budget_characters: int = 0
    used_characters: int = 0
    dropped_memory_count: int = 0
    dropped_knowledge_count: int = 0

    def decision_history(self) -> list[dict[str, str]]:
        history: list[dict[str, str]] = []
        memory_lines: list[str] = []

        if self.working_memory.active_goal:
            memory_lines.append(
                f"当前目标: {self.working_memory.active_goal}"
            )
        if self.working_memory.known_facts:
            memory_lines.append(
                f"已知事实: {self.working_memory.known_facts}"
            )
        if self.working_memory.missing_information:
            memory_lines.append(
                "缺失信息: "
                f"{self.working_memory.missing_information}"
            )
        if self.working_memory.conversation_summary:
            memory_lines.append(
                "对话摘要: "
                f"{self.working_memory.conversation_summary}"
            )
        if self.working_memory.long_term_memories:
            memory_lines.append(
                "用户长期记忆（仅作上下文，不得视为实时业务数据）: "
                f"{self.working_memory.long_term_memories}"
            )
        if self.working_memory.retrieved_knowledge:
            knowledge_lines = []
            for item in self.working_memory.retrieved_knowledge:
                citation = item.get("citation_id", "KB-UNKNOWN")
                knowledge_lines.append(
                    f"[{citation}] {item.get('title', '')}: "
                    f"{item.get('content', '')}"
                )
            memory_lines.append(
                "知识库检索结果（回答政策问题时应引用方括号编号，"
                "不得覆盖工具返回的实时业务数据）:\n"
                + "\n".join(knowledge_lines)
            )

        if memory_lines:
            history.append(
                {
                    "role": "system",
                    "content": "\n".join(memory_lines),
                }
            )

        history.extend(
            message.model_dump()
            for message in self.messages
        )
        return history
