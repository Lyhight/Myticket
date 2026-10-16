import pytest

from app.agent.entity_extractor import (
    RuleBasedEntityExtractor,
)


@pytest.fixture
def extractor() -> RuleBasedEntityExtractor:
    return RuleBasedEntityExtractor()


async def test_extract_explicit_order_id(extractor) -> None:
    result = await extractor.extract(
        title="查询订单",
        content="我的订单号是10001，请帮我查询",
    )

    assert result.entities["order_id"] == "10001"


async def test_extract_standalone_order_number(extractor) -> None:
    result = await extractor.extract(
        title="订单查询",
        content="帮我看看 12345678",
    )

    assert result.entities["order_id"] == "12345678"


async def test_extract_tracking_number(extractor) -> None:
    result = await extractor.extract(
        title="物流查询",
        content="快递单号为SF123456，请查询",
    )

    assert result.entities["tracking_number"] == "SF123456"


async def test_current_message_has_priority_over_history(
    extractor,
) -> None:
    result = await extractor.extract(
        title="订单查询",
        content="改查订单10002",
        history=[
            {
                "role": "user",
                "content": "之前查订单10001",
            },
        ],
    )

    assert result.entities["order_id"] == "10002"


async def test_extract_from_history(extractor) -> None:
    result = await extractor.extract(
        title="继续查询",
        content="就是刚才那个",
        history=[
            {
                "role": "user",
                "content": "订单号是10001",
            },
        ],
    )

    assert result.entities["order_id"] == "10001"


def test_missing_order_id_is_detected(extractor) -> None:
    missing = extractor.find_missing_fields(
        tool_name="get_order",
        entities={},
        tool_args={},
    )

    assert missing == ["order_id"]
    assert extractor.question_for(missing) == (
        "请提供需要查询的订单号。"
    )


def test_tool_arguments_satisfy_requirement(extractor) -> None:
    missing = extractor.find_missing_fields(
        tool_name="get_order",
        entities={},
        tool_args={"order_id": "10001"},
    )

    assert missing == []


def test_unknown_tool_has_no_declared_requirements(
    extractor,
) -> None:
    missing = extractor.find_missing_fields(
        tool_name="unknown_tool",
        entities={},
    )

    assert missing == []
