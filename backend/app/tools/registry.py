from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError


ToolFunction = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    function: ToolFunction
    argument_model: type[BaseModel]
    requires_user_context: bool = False
    allowed_categories: frozenset[str] = frozenset()
    risk_level: str = "low"
    timeout_seconds: float = 8.0
    max_retries: int = 0


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        func: ToolFunction,
        *,
        argument_model: type[BaseModel],
        requires_user_context: bool = False,
        allowed_categories: set[str] | None = None,
        risk_level: str = "low",
        timeout_seconds: float = 8.0,
        max_retries: int = 0,
    ) -> None:
        self._tools[name] = ToolDefinition(
            function=func,
            argument_model=argument_model,
            requires_user_context=requires_user_context,
            allowed_categories=frozenset(allowed_categories or set()),
            risk_level=risk_level,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    def definition(self, name: str) -> ToolDefinition:
        definition = self._tools.get(name)
        if definition is None:
            raise ValueError(f"Tool not registered: {name}")
        return definition

    def get(self, name: str) -> ToolFunction:
        return self.definition(name).function

    def validate_arguments(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        try:
            validated = self.definition(name).argument_model.model_validate(
                arguments
            )
        except ValidationError as exc:
            return None, exc.errors(
                include_url=False,
                include_input=False,
            )
        return validated.model_dump(), []

    def needs_user_context(self, name: str) -> bool:
        return self.definition(name).requires_user_context

    def exists(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())
