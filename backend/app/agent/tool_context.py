from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    """只能由后端创建的可信工具执行上下文。"""

    user_id: int
    ticket_id: int | None = None
    # 只能由管理员审批接口设置，永远不接收模型参数。
    human_approved: bool = False
