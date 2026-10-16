from app.tools.logistics_tools import (
    get_logistics,
)
from app.tools.order_tools import get_order
from app.tools.refund_tools import (
    check_refund_eligibility,
    create_refund_request,
)
from app.tools.registry import ToolRegistry
from app.tools.schemas import (
    CheckRefundEligibilityArguments,
    CreateRefundRequestArguments,
    GetLogisticsArguments,
    GetOrderArguments,
)


tool_registry = ToolRegistry()


tool_registry.register(
    "get_order",
    get_order,
    argument_model=GetOrderArguments,
    requires_user_context=True,
    allowed_categories={"ORDER", "LOGISTICS"},
    timeout_seconds=5.0,
    max_retries=1,
)

tool_registry.register(
    "get_logistics",
    get_logistics,
    argument_model=GetLogisticsArguments,
    requires_user_context=True,
    allowed_categories={"LOGISTICS"},
    timeout_seconds=5.0,
    max_retries=1,
)

tool_registry.register(
    "check_refund_eligibility",
    check_refund_eligibility,
    argument_model=CheckRefundEligibilityArguments,
    requires_user_context=True,
    allowed_categories={"REFUND"},
    timeout_seconds=5.0,
    max_retries=1,
)

tool_registry.register(
    "create_refund_request",
    create_refund_request,
    argument_model=CreateRefundRequestArguments,
    requires_user_context=True,
    allowed_categories={"REFUND"},
    risk_level="high",
    timeout_seconds=10.0,
)
