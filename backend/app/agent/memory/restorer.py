from app.agent.state import AgentState


class ShortTermMemoryRestorer:
    """把同一工单上一轮中可复用的工作记忆带入新一轮。"""

    def __init__(self, *, max_tool_results: int = 3) -> None:
        self.max_tool_results = max_tool_results

    def restore(
        self,
        *,
        state: AgentState,
        previous_state: AgentState | None,
    ) -> AgentState:
        if previous_state is None:
            return state

        if (
            state.ticket_id is not None
            and previous_state.ticket_id is not None
            and state.ticket_id != previous_state.ticket_id
        ):
            return state

        state.conversation_summary = previous_state.conversation_summary
        state.context_metadata = dict(previous_state.context_metadata)
        state.entities = dict(previous_state.entities)
        state.missing_fields = list(previous_state.missing_fields)
        state.tool_history = [
            item.model_copy(deep=True)
            for item in previous_state.tool_history[
                -self.max_tool_results:
            ]
        ]
        return state
