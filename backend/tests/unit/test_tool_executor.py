import pytest
from types import SimpleNamespace

from app.agent.schemas import AgentAction
from app.agent.tool_executor import ToolExecutor
from app.agent.tool_context import ToolExecutionContext


@pytest.mark.parametrize(
    "action_name",
    [
        "direct_reply",
        "ask_user",
    ],
)
async def test_action_without_tool_returns_none(
    action_name: str,
) -> None:
    executor = ToolExecutor()

    action = AgentAction(
        action=action_name,
        reason="No tool is required",
    )

    result = await executor.execute(action)

    assert result is None


async def test_missing_tool_name_returns_error() -> None:
    executor = ToolExecutor()

    action = AgentAction(
        action="tool",
        tool_name=None,
        reason="Tool name was not generated",
    )

    result = await executor.execute(action)

    assert result is not None
    assert result["success"] is False
    assert result["error"] == "MISSING_TOOL_NAME"


async def test_unregistered_tool_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = ToolExecutor()

    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.exists",
        lambda name: False,
    )

    action = AgentAction(
        action="tool",
        tool_name="unknown_tool",
        reason="Testing unknown tool",
    )

    result = await executor.execute(action)

    assert result is not None
    assert result["success"] is False
    assert result["error"] == "TOOL_NOT_FOUND"


async def test_registered_tool_is_executed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = ToolExecutor()

    received_arguments: dict = {}

    async def fake_get_order(
        order_id: str,
    ) -> dict:
        received_arguments["order_id"] = order_id

        return {
            "success": True,
            "order": {
                "order_id": order_id,
                "status": "PAID",
            },
        }

    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.exists",
        lambda name: True,
    )
    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.get",
        lambda name: fake_get_order,
    )
    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.definition",
        lambda name: SimpleNamespace(
            function=fake_get_order,
            requires_user_context=False,
            max_retries=1,
            risk_level="low",
            timeout_seconds=1,
            allowed_categories=None,
        ),
    )
    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.validate_arguments",
        lambda name, arguments: (dict(arguments), []),
    )
    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.needs_user_context",
        lambda name: False,
    )

    action = AgentAction(
        action="tool",
        tool_name="get_order",
        tool_args={
            "order_id": "10001",
        },
        reason="Query the customer order",
    )

    result = await executor.execute(action)

    assert result is not None
    assert result["success"] is True
    assert result["order"]["order_id"] == "10001"
    assert received_arguments == {
        "order_id": "10001",
    }


async def test_invalid_tool_arguments_return_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = ToolExecutor()

    async def fake_get_order(
        order_id: str,
    ) -> dict:
        return {
            "success": True,
            "order_id": order_id,
        }

    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.exists",
        lambda name: True,
    )
    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.get",
        lambda name: fake_get_order,
    )
    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.needs_user_context",
        lambda name: False,
    )

    action = AgentAction(
        action="tool",
        tool_name="get_order",
        tool_args={},
        reason="Missing order ID",
    )

    result = await executor.execute(action)

    assert result is not None
    assert result["success"] is False
    assert result["error"] == "INVALID_TOOL_ARGUMENTS"


async def test_tool_exception_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = ToolExecutor()

    async def broken_tool() -> dict:
        raise RuntimeError(
            "Business system unavailable"
        )

    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.exists",
        lambda name: True,
    )
    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.get",
        lambda name: broken_tool,
    )
    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.definition",
        lambda name: SimpleNamespace(
            function=broken_tool,
            requires_user_context=False,
            max_retries=0,
            risk_level="low",
            timeout_seconds=1,
            allowed_categories=None,
        ),
    )
    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.validate_arguments",
        lambda name, arguments: (dict(arguments), []),
    )
    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.needs_user_context",
        lambda name: False,
    )

    action = AgentAction(
        action="tool",
        tool_name="broken_tool",
        reason="Testing tool failure",
    )

    result = await executor.execute(action)

    assert result is not None
    assert result["success"] is False
    assert result["error"] == "TOOL_EXECUTION_FAILED"
    assert result["message"] == "Tool execution failed."


async def test_protected_tool_requires_context() -> None:
    executor = ToolExecutor()
    action = AgentAction(
        action="tool",
        tool_name="get_order",
        tool_args={"order_id": "10001"},
        reason="Query order",
    )

    result = await executor.execute(action)

    assert result is not None
    assert result["success"] is False
    assert result["error"] == "MISSING_USER_CONTEXT"


async def test_logistics_tool_requires_trusted_user_context() -> None:
    result = await ToolExecutor().execute(
        AgentAction(
            action="tool",
            tool_name="get_logistics",
            tool_args={"tracking_number": "SF123456"},
            reason="Query logistics",
        )
    )

    assert result is not None
    assert result["error"] == "MISSING_USER_CONTEXT"


async def test_trusted_user_id_overrides_model_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = ToolExecutor()
    received: dict = {}

    async def protected_tool(
        order_id: str,
        user_id: int,
    ) -> dict:
        received.update(
            order_id=order_id,
            user_id=user_id,
        )
        return {"success": True}

    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.exists",
        lambda name: True,
    )
    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.get",
        lambda name: protected_tool,
    )
    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.definition",
        lambda name: SimpleNamespace(
            function=protected_tool,
            requires_user_context=True,
            max_retries=0,
            risk_level="low",
            timeout_seconds=1,
            allowed_categories=None,
        ),
    )
    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.validate_arguments",
        lambda name, arguments: (dict(arguments), []),
    )
    monkeypatch.setattr(
        "app.agent.tool_executor.tool_registry.needs_user_context",
        lambda name: True,
    )

    action = AgentAction(
        action="tool",
        tool_name="get_order",
        tool_args={
            "order_id": "10001",
            "user_id": 999,
        },
        reason="Attempt to spoof user context",
    )

    result = await executor.execute(
        action,
        context=ToolExecutionContext(user_id=42),
    )

    assert result["success"] is True
    assert result["_execution"]["tool_name"] == "get_order"
    assert received == {
        "order_id": "10001",
        "user_id": 42,
    }
