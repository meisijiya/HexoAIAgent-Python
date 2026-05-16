"""
定时清理任务模块

功能：
- 每日凌晨自动过期：30 天无活动的会话 → 软删除其 messages/memories
- 定期物理删除：软删除超过 7 天的记录
"""
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select, update, delete
from loguru import logger

from app.core.database import async_session_maker
from app.models.session import Session
from app.models.message import Message
from app.models.memory import ConversationMemory


async def run_cleanup():
    """
    执行一轮清理：
    1. 软删除 30 天无活动的会话数据
    2. 物理删除 7 天前软删除的记录
    """
    async with async_session_maker() as db:
        # ── ① 自动过期：30 天无活动 ──
        cutoff_30d = datetime.utcnow() - timedelta(days=30)
        result = await db.execute(
            select(Session.id).where(
                Session.last_active_at < cutoff_30d,
                Session.last_active_at.isnot(None),
                Session.deleted_at.is_(None)
            )
        )
        expired_ids = [row[0] for row in result.all()]

        for sid in expired_ids:
            # Message 的 session_id 是 UUID 类型，直接用 sid
            await db.execute(
                update(Message)
                .where(Message.session_id == sid, Message.deleted_at.is_(None))
                .values(deleted_at=datetime.utcnow())
            )
            # ConversationMemory 的 session_id 是 String(36)，需转换
            sid_str = str(sid)
            await db.execute(
                update(ConversationMemory)
                .where(
                    ConversationMemory.session_id == sid_str,
                    ConversationMemory.deleted_at.is_(None)
                )
                .values(deleted_at=datetime.utcnow())
            )
            # 标记 session 为已删除
            await db.execute(
                update(Session)
                .where(Session.id == sid, Session.deleted_at.is_(None))
                .values(deleted_at=datetime.utcnow())
            )
        await db.commit()
        logger.info(f"自动过期清理：软删除 {len(expired_ids)} 个会话的数据")

        # ── ② 物理删除：软删除 > 7 天 ──
        cutoff_7d = datetime.utcnow() - timedelta(days=7)
        msg_del = await db.execute(
            delete(Message).where(Message.deleted_at < cutoff_7d)
        )
        mem_del = await db.execute(
            delete(ConversationMemory).where(ConversationMemory.deleted_at < cutoff_7d)
        )
        await db.commit()
        logger.info(
            f"物理删除清理：messages={msg_del.rowcount}, memories={mem_del.rowcount}"
        )


async def _cleanup_loop():
    """
    后台清理循环：每天凌晨 3 点执行清理
    """
    while True:
        now = datetime.utcnow()
        next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()
        logger.info(f"清理任务：等待 {wait_seconds / 3600:.1f} 小时后执行")

        try:
            await asyncio.sleep(wait_seconds)
            await run_cleanup()
        except asyncio.CancelledError:
            # 正常关闭信号，不做日志记录
            raise
        except Exception as e:
            logger.error(f"清理任务异常: {e}")
            # 出错后等 1 小时再重试（避免 rapid fire）
            await asyncio.sleep(3600)
