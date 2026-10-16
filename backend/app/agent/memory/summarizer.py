from app.agent.state import ConversationTurn


class RollingConversationSummarizer:
    """把被上下文预算裁剪的旧消息压缩为有界的滚动摘要。"""

    ROLE_LABELS = {
        "user": "用户",
        "assistant": "客服",
        "system": "系统",
    }

    def __init__(
        self,
        *,
        max_summary_characters: int = 1200,
        max_message_characters: int = 240,
    ) -> None:
        self.max_summary_characters = max_summary_characters
        self.max_message_characters = max_message_characters

    def summarize(
        self,
        *,
        previous_summary: str | None,
        omitted_messages: list[ConversationTurn],
    ) -> str | None:
        if not omitted_messages:
            return previous_summary

        parts: list[str] = []

        if previous_summary:
            parts.append(previous_summary.strip())

        for message in omitted_messages:
            content = " ".join(message.content.split())
            if len(content) > self.max_message_characters:
                content = (
                    content[: self.max_message_characters - 1]
                    + "…"
                )

            label = self.ROLE_LABELS.get(message.role, message.role)
            parts.append(f"{label}: {content}")

        summary = " | ".join(part for part in parts if part)

        if len(summary) <= self.max_summary_characters:
            return summary or None

        # 保留摘要末尾，因为这里包含时间上更新、通常更相关的信息。
        return "…" + summary[-(self.max_summary_characters - 1) :]
