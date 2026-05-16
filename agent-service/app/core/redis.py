"""
Redis 连接模块

负责：
- 创建 Redis 连接池
- 提供依赖注入函数
- 封装常用操作
"""
import json
from typing import Optional
import redis.asyncio as redis
from loguru import logger

from app.config import settings


# Redis 连接池
redis_pool: Optional[redis.Redis] = None


async def init_redis() -> redis.Redis:
    """
    初始化 Redis 连接
    
    Returns:
        redis.Redis: Redis 连接实例
    """
    global redis_pool
    
    try:
        redis_pool = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
        
        # 测试连接
        await redis_pool.ping()
        logger.info("✅ Redis 连接成功")
        
        return redis_pool
        
    except Exception as e:
        logger.error(f"❌ Redis 连接失败: {e}")
        raise


async def close_redis():
    """
    关闭 Redis 连接
    
    在应用关闭时调用
    """
    global redis_pool
    
    if redis_pool:
        await redis_pool.close()
        redis_pool = None
        logger.info("👋 Redis 连接已关闭")


async def get_redis() -> redis.Redis:
    """
    获取 Redis 连接（依赖注入）
    
    用于 FastAPI 的依赖注入系统
    
    Returns:
        redis.Redis: Redis 连接实例
    """
    global redis_pool
    
    if redis_pool is None:
        raise RuntimeError("Redis 未初始化")
    
    return redis_pool


# ==================== 会话上下文管理 ====================

async def get_session_context(session_id: str, max_messages: int = 10) -> list:
    """
    获取会话上下文（短期记忆）
    
    Args:
        session_id: 会话 ID
        max_messages: 最大消息数量
    
    Returns:
        list: 消息列表
    """
    redis_client = await get_redis()
    key = f"session:{session_id}:context"
    
    # 用 lpush 插入，新消息在左端（索引 0）。此处反转回时间正序（旧→新）
    messages = await redis_client.lrange(key, 0, max_messages - 1)
    messages.reverse()
    
    return [json.loads(msg) for msg in messages]


async def add_message_to_context(session_id: str, role: str, content: str, ttl: int = 86400):
    """
    添加消息到会话上下文
    
    Args:
        session_id: 会话 ID
        role: 消息角色 (user/assistant)
        content: 消息内容
        ttl: 过期时间（秒），默认 24 小时
    """
    redis_client = await get_redis()
    key = f"session:{session_id}:context"
    
    message = json.dumps({
        "role": role,
        "content": content
    })
    
    # 添加到列表头部，新消息在左端（索引0），配合 ltrim/lrange 保留最新消息
    await redis_client.lpush(key, message)
    
    # 保留最近 20 条消息
    await redis_client.ltrim(key, 0, 19)
    
    # 设置过期时间
    await redis_client.expire(key, ttl)


async def clear_session_context(session_id: str):
    """
    清空会话上下文
    
    Args:
        session_id: 会话 ID
    """
    redis_client = await get_redis()
    key = f"session:{session_id}:context"
    
    await redis_client.delete(key)


# ==================== 用户会话列表缓存 ====================

async def cache_user_sessions(user_id: str, session_ids: list, ttl: int = 3600):
    """
    缓存用户的会话列表
    
    Args:
        user_id: 用户 ID
        session_ids: 会话 ID 列表
        ttl: 过期时间（秒），默认 1 小时
    """
    redis_client = await get_redis()
    key = f"user:{user_id}:sessions"
    
    # 清空旧数据
    await redis_client.delete(key)
    
    # 添加新数据
    if session_ids:
        await redis_client.rpush(key, *session_ids)
    
    # 设置过期时间
    await redis_client.expire(key, ttl)


async def get_cached_user_sessions(user_id: str) -> list:
    """
    获取缓存的用户会话列表
    
    Args:
        user_id: 用户 ID
    
    Returns:
        list: 会话 ID 列表
    """
    redis_client = await get_redis()
    key = f"user:{user_id}:sessions"
    
    return await redis_client.lrange(key, 0, -1)


# ==================== OAuth 状态缓存 ====================

async def cache_oauth_state(state: str, redirect_url: str, ttl: int = 600):
    """
    缓存 OAuth 状态
    
    Args:
        state: OAuth state 参数
        redirect_url: 重定向 URL
        ttl: 过期时间（秒），默认 10 分钟
    """
    redis_client = await get_redis()
    key = f"oauth:state:{state}"
    
    await redis_client.setex(key, ttl, redirect_url)


async def get_oauth_state(state: str) -> Optional[str]:
    """
    获取 OAuth 状态
    
    Args:
        state: OAuth state 参数
    
    Returns:
        Optional[str]: 重定向 URL
    """
    redis_client = await get_redis()
    key = f"oauth:state:{state}"
    
    value = await redis_client.get(key)
    
    # 使用后删除
    if value:
        await redis_client.delete(key)
    
    return value


# ==================== API 限流 ====================

async def check_rate_limit(user_id: str, limit: int = 30, window: int = 60) -> bool:
    """
    检查 API 限流
    
    Args:
        user_id: 用户 ID
        limit: 限制次数
        window: 时间窗口（秒）
    
    Returns:
        bool: 是否允许访问
    """
    redis_client = await get_redis()
    key = f"rate:{user_id}"
    
    # 获取当前计数
    current = await redis_client.get(key)
    
    if current is None:
        # 首次访问
        await redis_client.setex(key, window, 1)
        return True
    
    if int(current) >= limit:
        # 超过限制
        return False
    
    # 增加计数
    await redis_client.incr(key)
    return True


# ==================== 会话清理工具 ====================

async def clear_session_redis(session_id: str) -> dict:
    """
    清除会话的 Redis 数据（不删除 rate 限流键）

    清除 session:{id}:context 和 round_counter:{id} 两个键。
    保留 rate:{user_id}（全局限流）、embedding:*（知识库缓存）、oauth:state:*（OAuth 状态）。

    Args:
        session_id: 会话 ID

    Returns:
        dict: 包含每个键的删除结果 {'context_deleted': bool, 'counter_deleted': bool}
    """
    redis_client = await get_redis()
    results = {}

    # 清除 session context（List）
    context_key = f"session:{session_id}:context"
    try:
        deleted = await redis_client.delete(context_key)
        results["context_deleted"] = deleted >= 0
    except Exception as e:
        logger.warning(f"清除 session context 失败: {context_key}, error={e}")
        results["context_deleted"] = False

    # 清除 round counter
    counter_key = f"round_counter:{session_id}"
    try:
        deleted = await redis_client.delete(counter_key)
        results["counter_deleted"] = deleted >= 0
    except Exception as e:
        logger.warning(f"清除 round counter 失败: {counter_key}, error={e}")
        results["counter_deleted"] = False

    logger.info(f"Redis session cleanup for {session_id}: {results}")
    return results


# ==================== 每日限流 ====================

async def check_daily_limit(identifier: str, limit: int) -> tuple:
    """
    每日限流检查（基于日期滚动 Key）

    Key 格式: daily_rate:{identifier}:{YYYY-MM-DD}

    Returns:
        (bool, int): (是否允许, 剩余次数)
    """
    from datetime import datetime, timedelta

    redis_client = await get_redis()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    key = f"daily_rate:{identifier}:{today}"

    current = await redis_client.get(key)

    if current is None:
        tomorrow = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        expire_seconds = int((tomorrow - datetime.utcnow()).total_seconds()) + 1
        await redis_client.setex(key, expire_seconds, 1)
        return True, limit - 1

    count = int(current)
    if count >= limit:
        return False, 0

    await redis_client.incr(key)
    return True, limit - count - 1
