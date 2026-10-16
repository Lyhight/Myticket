from dataclasses import dataclass, field

from app.agent.schemas import AgentAction
from app.agent.state import AgentState
from app.tools import tool_registry


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    issues: list[str] = field(default_factory=list)


class ActionPolicy:
    """LLM 动作与实际工具执行之间的确定性授权层。"""

    def evaluate(
        self,
        action: AgentAction,
        state: AgentState | None,
        *,
        trusted_human_approval: bool = False,
    ) -> PolicyDecision:
        if action.action != "tool":
            return PolicyDecision(True)
        if not action.tool_name or not tool_registry.exists(action.tool_name):
            return PolicyDecision(False, ["工具不存在或未注册"])

        definition = tool_registry.definition(action.tool_name)
        issues: list[str] = []
        if (
            state is not None
            and definition.allowed_categories
            and state.category not in definition.allowed_categories
        ):
            issues.append(
                f"类别 {state.category} 不允许调用 {action.tool_name}"
            )

        if definition.risk_level == "high":
            confirmed = action.tool_args.get("confirmed") is True
            state_confirmed = bool(
                state
                and action.tool_name in state.confirmed_actions
            )
            if not (
                (confirmed and state_confirmed)
                or trusted_human_approval
            ):
                issues.append("高风险工具缺少有效的用户确认或人工批准")

        return PolicyDecision(not issues, issues)
