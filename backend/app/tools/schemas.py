from pydantic import BaseModel, ConfigDict, Field


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GetOrderArguments(ToolArguments):
    order_id: str = Field(min_length=1, max_length=50)


class GetLogisticsArguments(ToolArguments):
    tracking_number: str = Field(min_length=1, max_length=50)


class CheckRefundEligibilityArguments(ToolArguments):
    order_id: str = Field(min_length=1, max_length=50)


class CreateRefundRequestArguments(ToolArguments):
    order_id: str = Field(min_length=1, max_length=50)
    reason: str = Field(min_length=2, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=100)
    confirmed: bool = False
    human_approved: bool = False
