import re
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class EntityExtraction(BaseModel):
    entities: dict[str, str] = Field(default_factory=dict)


class BaseEntityExtractor(ABC):

    @abstractmethod
    async def extract(
        self,
        *,
        title: str,
        content: str,
        history: list[dict[str, str]] | None = None,
    ) -> EntityExtraction:
        raise NotImplementedError


class RuleBasedEntityExtractor(BaseEntityExtractor):
    """提取可被严格验证的业务标识，避免让模型编造参数。"""

    TOOL_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
        "get_order": ("order_id",),
        "get_logistics": ("tracking_number",),
    }

    FIELD_QUESTIONS: dict[str, str] = {
        "order_id": "请提供需要查询的订单号。",
        "tracking_number": "请提供需要查询的物流单号。",
    }

    ORDER_PATTERNS = (
        re.compile(
            r"(?:订单号|订单)\s*(?:是|为|[:：])?\s*"
            r"([A-Za-z0-9_-]{4,32})",
            re.IGNORECASE,
        ),
        re.compile(r"\b(\d{5,32})\b"),
    )

    TRACKING_PATTERNS = (
        re.compile(
            r"(?:物流单号|运单号|快递单号)\s*"
            r"(?:是|为|[:：])?\s*"
            r"([A-Za-z0-9_-]{6,32})",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b((?:SF|YT|ZTO|STO|YD|JD)\d{6,24})\b",
            re.IGNORECASE,
        ),
    )

    async def extract(
        self,
        *,
        title: str,
        content: str,
        history: list[dict[str, str]] | None = None,
    ) -> EntityExtraction:
        entities: dict[str, str] = {}

        # 当前消息优先，其次标题，最后从最近的历史消息回溯。
        texts = [content, title]
        texts.extend(
            str(item.get("content", ""))
            for item in reversed(history or [])
        )

        for text in texts:
            self._extract_first(
                entities,
                field="tracking_number",
                text=text,
                patterns=self.TRACKING_PATTERNS,
            )
            self._extract_first(
                entities,
                field="order_id",
                text=text,
                patterns=self.ORDER_PATTERNS,
            )

        return EntityExtraction(entities=entities)

    @staticmethod
    def _extract_first(
        entities: dict[str, str],
        *,
        field: str,
        text: str,
        patterns: tuple[re.Pattern[str], ...],
    ) -> None:
        if field in entities:
            return

        for pattern in patterns:
            match = pattern.search(text)

            if match:
                entities[field] = match.group(1)
                return

    def required_fields_for_tool(
        self,
        tool_name: str | None,
    ) -> tuple[str, ...]:
        if tool_name is None:
            return ()

        return self.TOOL_REQUIRED_FIELDS.get(tool_name, ())

    def find_missing_fields(
        self,
        *,
        tool_name: str | None,
        entities: dict[str, Any],
        tool_args: dict[str, Any] | None = None,
    ) -> list[str]:
        available = dict(entities)
        available.update(tool_args or {})

        return [
            field
            for field in self.required_fields_for_tool(tool_name)
            if not available.get(field)
        ]

    def question_for(
        self,
        missing_fields: list[str],
    ) -> str:
        if not missing_fields:
            return "请补充完成操作所需的信息。"

        return self.FIELD_QUESTIONS.get(
            missing_fields[0],
            f"请补充信息：{missing_fields[0]}。",
        )
