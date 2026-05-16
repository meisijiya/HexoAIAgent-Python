"""pytest 配置和 fixtures"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# 添加 app 目录到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 尝试导入 app 模块（生产代码可能有 SQLAlchemy 兼容性问题）
# 如果导入失败，相关 fixture 会在使用时报错而非阻断所有测试
app = None
database = None
redis = None
try:
    from app.main import app
    from app.core import database, redis
except Exception as e:
    import warnings
    warnings.warn(f"导入 app 模块失败: {e}")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def async_client():
    """创建 AsyncClient 用于测试 FastAPI"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def mock_db_session(mocker):
    """Mock 数据库会话"""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()
    
    async def override_get_db():
        yield mock_session
    
    app.dependency_overrides[database.get_db] = override_get_db
    yield mock_session
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def mock_redis(mocker):
    """Mock Redis 连接"""
    mock_redis_client = AsyncMock()
    mock_redis_client.ping = AsyncMock(return_value=True)
    mock_redis_client.get = AsyncMock(return_value=None)
    mock_redis_client.set = AsyncMock(return_value=True)
    mock_redis_client.lrange = AsyncMock(return_value=[])
    mock_redis_client.rpush = AsyncMock(return_value=1)
    mock_redis_client.ltrim = AsyncMock(return_value=True)
    mock_redis_client.expire = AsyncMock(return_value=True)
    
    mocker.patch("app.core.redis.get_redis", return_value=mock_redis_client)
    mocker.patch("app.core.redis.redis_pool", mock_redis_client)
    yield mock_redis_client


@pytest.fixture
def test_user_token():
    """生成测试用户 token"""
    from app.auth.token import create_access_token
    return create_access_token("test-user-id")


@pytest.fixture
def test_user():
    """测试用户数据"""
    return {
        "id": "test-user-id",
        "nickname": "测试老江湖",
        "github_id": "12345",
        "github_username": "laojianghu",
        "email": "test@example.com",
        "avatar_url": "https://example.com/avatar.png",
        "is_anonymous": False
    }
