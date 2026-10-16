import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.repositories.user_memory_repository import (
    UserMemoryRepository,
)


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    memory_type: str
    content: str
    fingerprint: str
    memory_key: str
    confidence: float = 1.0


class ExplicitMemoryExtractor:
    """只提取用户明确表达的偏好或记忆请求。"""

    PATTERNS = (
        (
            "preference",
            re.compile(r"我(?:喜欢|偏好)[，,:： ]*(.{2,200})"),
        ),
        (
            "explicit",
            re.compile(r"(?:请记住|记一下)[，,:： ]*(.{2,200})"),
        ),
    )
    SENSITIVE_TERMS = (
        "密码",
        "验证码",
        "身份证",
        "银行卡",
        "信用卡",
        "access_token",
        "refresh_token",
        "api_key",
        "secret",
    )

    @staticmethod
    def _memory_key(value: str, memory_type: str) -> str:
        lowered = value.lower()
        if any(term in lowered for term in ("中文", "英文", "语言", "回复")):
            return "response_language"
        if any(term in lowered for term in ("短信", "电话", "邮件", "通知")):
            return "notification_channel"
        if any(term in lowered for term in ("称呼", "叫我")):
            return "salutation"
        return hashlib.sha256(
            f"{memory_type}:{lowered}".encode("utf-8")
        ).hexdigest()[:32]

    def extract(self, content: str) -> list[MemoryCandidate]:
        normalized = " ".join(content.strip().split())
        lowered = normalized.lower()

        if any(term in lowered for term in self.SENSITIVE_TERMS):
            return []

        candidates: list[MemoryCandidate] = []
        seen: set[str] = set()

        for memory_type, pattern in self.PATTERNS:
            match = pattern.search(normalized)
            if not match:
                continue

            value = match.group(1).strip("。！!，, ")
            if not value:
                continue

            memory_content = (
                f"用户偏好：{value}"
                if memory_type == "preference"
                else f"用户明确要求记住：{value}"
            )
            fingerprint = hashlib.sha256(
                f"{memory_type}:{value.lower()}".encode("utf-8")
            ).hexdigest()
            memory_key = self._memory_key(value, memory_type)

            if fingerprint not in seen:
                candidates.append(
                    MemoryCandidate(
                        memory_type=memory_type,
                        content=memory_content,
                        fingerprint=fingerprint,
                        memory_key=memory_key,
                    )
                )
                seen.add(fingerprint)

        return candidates


class LongTermMemoryService:
    def __init__(self, repository: UserMemoryRepository):
        self.repository = repository
        self.extractor = ExplicitMemoryExtractor()

    async def recall(
        self,
        user_id: int,
        *,
        limit: int = 10,
    ) -> list[dict[str, str | float]]:
        memories = await self.repository.list_active_by_user(
            user_id,
            limit=limit,
        )
        return [
            {
                "type": item.memory_type,
                "content": item.content,
                "confidence": item.confidence,
                "memory_key": item.memory_key,
                "expires_at": (
                    item.expires_at.isoformat()
                    if item.expires_at
                    else None
                ),
            }
            for item in memories
        ]

    async def remember_from_message(
        self,
        *,
        user_id: int,
        ticket_id: int | None,
        content: str,
    ) -> int:
        candidates = self.extractor.extract(content)

        for candidate in candidates:
            await self.repository.deactivate_conflicts(
                user_id=user_id,
                memory_key=candidate.memory_key,
                keep_fingerprint=candidate.fingerprint,
            )
            await self.repository.upsert(
                user_id=user_id,
                memory_type=candidate.memory_type,
                content=candidate.content,
                fingerprint=candidate.fingerprint,
                memory_key=candidate.memory_key,
                source_ticket_id=ticket_id,
                confidence=candidate.confidence,
                expires_at=(
                    datetime.now(timezone.utc).replace(tzinfo=None)
                    + timedelta(days=180)
                ),
            )

        return len(candidates)
