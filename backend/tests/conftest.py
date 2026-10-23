import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool


# 测试进程只使用隔离配置，不连接真实 MySQL 或模型服务。
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["JWT_SECRET"] = (
    "test-jwt-secret-at-least-32-bytes-long"
)
os.environ["DASHSCOPE_API_KEY"] = "test-api-key"
os.environ["DEBUG"] = "false"
os.environ["EMBEDDING_ENABLED"] = "false"
os.environ["QDRANT_ENABLED"] = "false"

# 必须在环境变量设置完成后导入应用模块。
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402, F401
from app.api.v1.auth import (  # noqa: E402
    auth_account_rate_limiter,
    auth_ip_rate_limiter,
)
from app.api.v1.tickets import agent_rate_limiter  # noqa: E402


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """为每个测试创建独立的内存数据库。"""

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """让 FastAPI 在测试中使用隔离数据库。"""

    auth_account_rate_limiter.reset()
    auth_ip_rate_limiter.reset()
    agent_rate_limiter.reset()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        email="admin@example.com",
        password_hash=hash_password("admin-password"),
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user
