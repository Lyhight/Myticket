import re
from typing import Literal


ConfirmationIntent = Literal[
    "confirm",
    "reject",
    "unknown",
]


class ConfirmationDetector:
    """保守识别用户是否明确确认高风险操作。"""

    CONFIRM_PATTERNS = (
        re.compile(r"^(确认|确定|同意|是的|确认执行|确认退款)[。！! ]*$"),
        re.compile(r"^好的?[，, ]*(确认|确定)[。！! ]*$"),
    )
    REJECT_PATTERNS = (
        re.compile(r"^(取消|拒绝|不同意|不确认|算了|先不要|不要了)[。！! ]*$"),
        re.compile(r"^不[，, ]*(退款|执行|取消订单)[。！! ]*$"),
    )

    def detect(self, content: str) -> ConfirmationIntent:
        normalized = content.strip().lower()

        if not normalized:
            return "unknown"

        # 必须先判断否定，避免把“不确认”误识别为“确认”。
        if any(
            pattern.fullmatch(normalized)
            for pattern in self.REJECT_PATTERNS
        ):
            return "reject"

        if any(
            pattern.fullmatch(normalized)
            for pattern in self.CONFIRM_PATTERNS
        ):
            return "confirm"

        return "unknown"
