from typing import Any

from app.agent.schemas import CustomerServiceAgentResult
from app.agent.state import AgentState
from app.agent.versioning import PROMPT_VERSIONS
from app.core.config import settings


def build_llm_telemetry(
    *,
    state: AgentState | None,
    result: CustomerServiceAgentResult,
) -> dict[str, Any]:
    """SDK 未暴露统一 usage 时采用保守字符估算，并明确标记来源。"""
    input_characters = 0
    if state is not None:
        input_characters = len(state.title) + len(state.user_message)
        input_characters += sum(len(item.content) for item in state.history)
        input_characters += len(str(state.context_metadata))
        input_characters += len(str(state.long_term_memories))
        input_characters += len(str(state.retrieved_knowledge))
    output_characters = len(result.reply or "")
    input_tokens = max(1, input_characters // 2)
    output_tokens = max(1, output_characters // 2)
    return {
        "model_provider": (
            settings.llm_provider if settings.llm_enabled else "offline_rules"
        ),
        "model_name": (
            settings.qwen_model if settings.llm_enabled else "rule-based-v1"
        ),
        "prompt_versions": dict(PROMPT_VERSIONS),
        "token_usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "source": "character_estimate",
        },
    }
