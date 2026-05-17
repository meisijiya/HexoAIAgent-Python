"""
数据库连接模块

负责：
- 创建 SQLAlchemy 异步引擎
- 管理数据库会话
- 提供依赖注入函数
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from loguru import logger

from app.config import settings


# 创建异步引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,  # 调试模式下打印 SQL
    pool_size=5,          # 连接池大小
    max_overflow=10,      # 最大溢出连接数
)

# 创建异步会话工厂
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


class Base(DeclarativeBase):
    """
    SQLAlchemy 模型基类
    
    所有数据模型都继承此类
    """
    pass


async def get_db() -> AsyncSession:
    """
    获取数据库会话（依赖注入）
    
    用于 FastAPI 的依赖注入系统
    
    Yields:
        AsyncSession: 数据库会话
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"数据库操作失败: {e}")
            raise
        finally:
            await session.close()


async def init_db():
    """
    初始化数据库
    
    创建所有表结构 + GIN 索引
    """
    from sqlalchemy import text
    
    async with engine.begin() as conn:
        # 导入所有模型以确保它们被注册
        from app.models import Base
        await conn.run_sync(Base.metadata.create_all)
        
        # 创建 GIN 索引（init-db.sql 执行时表还不存在，这里补充）
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_chunks_metadata_gin "
            "ON knowledge_chunks USING GIN (metadata)"
        ))
    logger.info("✅ 数据库表创建完成")


async def close_db():
    """
    关闭数据库连接
    
    在应用关闭时调用
    """
    await engine.dispose()
    logger.info("👋 数据库连接已关闭")
