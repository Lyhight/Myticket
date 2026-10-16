import re
import unicodedata
from typing import Any


INJECTION_PATTERNS = (
    re.compile(r"忽略.{0,20}(之前|以上|系统).{0,20}(指令|规则)"),
    re.compile(r"(泄露|显示|输出).{0,12}(系统提示词|system prompt)", re.I),
    re.compile(r"ignore.{0,20}(previous|system).{0,20}instructions", re.I),
    re.compile(r"(developer|system)\s*message\s*:", re.I),
    re.compile(r"(隐藏|内部|后台).{0,12}(提示|规则|指令).{0,12}(输出|打印|展示|告诉)", re.I),
    re.compile(r"(输出|打印|展示|告诉).{0,12}(隐藏|内部|后台).{0,12}(提示|规则|指令)", re.I),
    re.compile(r"(扮演|作为|变成).{0,12}(系统|管理员|开发者)", re.I),
    re.compile(r"ignore.{0,20}(earlier|all).{0,20}(rules|instructions)", re.I),
    re.compile(r"reveal.{0,20}(developer|system).{0,20}(prompt|message)", re.I),
)


class InputGuard:
    @staticmethod
    def normalize(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text).lower()
        # A second compact representation catches simple whitespace and
        # punctuation splitting without changing the text sent downstream.
        return re.sub(r"[\s\W_]+", "", normalized, flags=re.UNICODE)

    @staticmethod
    def issues(text: str) -> list[str]:
        normalized = unicodedata.normalize("NFKC", text).lower()
        compact = InputGuard.normalize(text)
        return [
            "检测到疑似提示词注入"
            for pattern in INJECTION_PATTERNS
            if pattern.search(normalized) or pattern.search(compact)
        ][:1]

    @staticmethod
    def sanitize_knowledge(
        items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int]:
        safe: list[dict[str, Any]] = []
        rejected = 0
        for item in items:
            if InputGuard.issues(str(item.get("content", ""))):
                rejected += 1
            else:
                safe.append(item)
        return safe, rejected


class PrivacyGuard:
    PATTERNS = (
        ("可能包含银行卡号", re.compile(r"(?<!\d)\d{16,19}(?!\d)")),
        ("可能包含身份证号", re.compile(r"(?<!\d)\d{17}[\dXx](?!\w)")),
        (
            "可能包含访问密钥",
            re.compile(
                r"(access[_ -]?token|api[_ -]?key|secret)\s*[:=]\s*\S+",
                re.I,
            ),
        ),
        (
            "可能包含验证码",
            re.compile(r"(验证码|verification code).{0,8}\b\d{4,8}\b", re.I),
        ),
    )

    @classmethod
    def issues(cls, text: str) -> list[str]:
        issues = [
            label
            for label, pattern in cls.PATTERNS
            if pattern.search(text)
        ]
        compact_digits = re.sub(r"[\s-]", "", text)
        if (
            "可能包含银行卡号" not in issues
            and re.search(r"(?<!\d)\d{16,19}(?!\d)", compact_digits)
        ):
            issues.append("可能包含银行卡号")
        if (
            "可能包含身份证号" not in issues
            and re.search(r"(?<!\d)\d{17}[\dXx](?!\w)", compact_digits)
        ):
            issues.append("可能包含身份证号")
        return issues
