from app.agent.memory.long_term import (
    ExplicitMemoryExtractor,
    LongTermMemoryService,
)
from app.models.user import User
from app.repositories.user_memory_repository import (
    UserMemoryRepository,
)


def test_extractor_accepts_explicit_preferences() -> None:
    candidates = ExplicitMemoryExtractor().extract(
        "我喜欢短信通知，请及时告诉我结果。"
    )

    assert len(candidates) == 1
    assert candidates[0].memory_type == "preference"
    assert "短信通知" in candidates[0].content


def test_extractor_rejects_sensitive_information() -> None:
    candidates = ExplicitMemoryExtractor().extract(
        "请记住我的银行卡是6222000012345678"
    )

    assert candidates == []


def test_extractor_ignores_ordinary_messages() -> None:
    assert ExplicitMemoryExtractor().extract(
        "帮我查询订单10001"
    ) == []


async def test_memory_service_persists_deduplicates_and_recalls(
    db_session,
) -> None:
    user = User(
        email="memory@example.com",
        password_hash="test-hash",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    service = LongTermMemoryService(
        UserMemoryRepository(db_session)
    )
    first_count = await service.remember_from_message(
        user_id=user.id,
        ticket_id=None,
        content="请记住以后优先用中文回复。",
    )
    second_count = await service.remember_from_message(
        user_id=user.id,
        ticket_id=None,
        content="请记住以后优先用中文回复。",
    )

    memories = await service.recall(user.id)

    assert first_count == 1
    assert second_count == 1
    assert len(memories) == 1
    assert memories[0]["type"] == "explicit"
    assert "中文回复" in str(memories[0]["content"])
    assert memories[0]["memory_key"] == "response_language"
    assert memories[0]["expires_at"] is not None


async def test_new_preference_deactivates_conflicting_memory(
    db_session,
) -> None:
    user = User(
        email="memory-conflict@example.com",
        password_hash="test-hash",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    service = LongTermMemoryService(UserMemoryRepository(db_session))

    await service.remember_from_message(
        user_id=user.id,
        ticket_id=None,
        content="我喜欢短信通知",
    )
    await service.remember_from_message(
        user_id=user.id,
        ticket_id=None,
        content="我喜欢邮件通知",
    )
    memories = await service.recall(user.id)

    assert len(memories) == 1
    assert "邮件通知" in str(memories[0]["content"])
