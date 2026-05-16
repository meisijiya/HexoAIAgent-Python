"""
对话 API 路由模块

提供对话相关接口，使用调度器协调多个 Agent
"""
import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from loguru import logger

from app.core.database import get_db
from app.core.redis import check_daily_limit, check_rate_limit, clear_session_redis
from app.agents.chat_agent import chat_agent
from app.models.session import Session
from app.models.message import Message
from app.models.memory import ConversationMemory
from app.models.user import User
from app.auth.token import verify_token

router = APIRouter(prefix="/api/chat", tags=["对话"])


class ChatRequest(BaseModel):
    """对话请求模型"""
    message: str
    session_id: Optional[str] = None
    command: Optional[str] = None
    token: Optional[str] = None


@router.delete("/session/{session_id}")
async def delete_session(session_id: str, token: str, db: AsyncSession = Depends(get_db)):
    """
    清除会话：Redis 数据清理 + PG 软删除
    
    Args:
        session_id: 会话 ID
        token: JWT Token
    
    Returns:
        dict: 清理结果统计
    """
    # 1. 权限校验
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的 Token")
    
    # 验证会话存在且属于当前用户
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.user_id == user_id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    try:
        # 2. Redis 清理（短期记忆 + round counter）
        await clear_session_redis(session_id)
        
        # 3. PG 软删除 messages
        msg_result = await db.execute(
            update(Message)
            .where(Message.session_id == session_id, Message.deleted_at == None)
            .values(deleted_at=datetime.utcnow())
        )
        deleted_messages = msg_result.rowcount
        
        # 4. PG 软删除 memories（向量记忆）
        mem_result = await db.execute(
            update(ConversationMemory)
            .where(ConversationMemory.session_id == session_id, ConversationMemory.deleted_at == None)
            .values(deleted_at=datetime.utcnow())
        )
        deleted_memories = mem_result.rowcount
        
        # 5. 软删除 session（保留元数据行，标记删除时间）
        session.deleted_at = datetime.utcnow()
        session.last_active_at = None
        
        # 6. 提交事务
        await db.commit()
        
        logger.info(f"已清除会话 {session_id}: messages={deleted_messages}, memories={deleted_memories}")
        
        return {
            "ok": True,
            "deleted_messages": deleted_messages,
            "deleted_memories": deleted_memories
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"清除会话失败: {e}")
        raise HTTPException(status_code=500, detail=f"清除失败: {str(e)}")


@router.post("")
async def chat(chat_req: ChatRequest, fastapi_request: Request, db: AsyncSession = Depends(get_db)):
    """
    对话接口（流式输出）
    
    ChatAgent 作为唯一入口，LLM 判断意图后路由到对应子 Agent
    
    Args:
        chat_req: 对话请求
    
    Returns:
        StreamingResponse: 流式响应
    """
    # 验证身份：优先使用 Token，匿名则提取 IP
    is_anonymous = False
    user_id = None
    client_ip = None

    if chat_req.token:
        user_id = verify_token(chat_req.token)
    
    if user_id:
        # 查库确认是否为匿名用户（匿名登录也会发 JWT）
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user and user.is_anonymous:
            is_anonymous = True
            client_ip = fastapi_request.client.host if fastapi_request.client else "unknown"
        else:
            is_anonymous = False
    else:
        is_anonymous = True
        client_ip = fastapi_request.client.host if fastapi_request.client else "unknown"
    
    # 每日限流
    if is_anonymous:
        identifier = f"ip:{client_ip}"
        daily_limit = 10
    else:
        identifier = f"user:{user_id}"
        daily_limit = 100

    daily_allowed, daily_remaining = await check_daily_limit(identifier, daily_limit)
    if not daily_allowed:
        raise HTTPException(status_code=429, detail=f"今日请求次数已达上限（{daily_limit}次），请明天再试")

    # 60s 突发限流
    rate_id = client_ip if is_anonymous else user_id
    if not await check_rate_limit(rate_id):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    
    # 获取或创建会话
    session_id = chat_req.session_id
    
    if not is_anonymous:
        if not session_id:
            # 创建新会话
            session = Session(
                user_id=user_id,
                title=chat_req.message[:50] + "..." if len(chat_req.message) > 50 else chat_req.message
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)
            session_id = str(session.id)
            logger.info(f"创建新会话: {session_id}")
        else:
            # 验证会话存在且属于当前用户
            result = await db.execute(
                select(Session).where(
                    Session.id == session_id,
                    Session.user_id == user_id
                )
            )
            session = result.scalar_one_or_none()
            if not session:
                raise HTTPException(status_code=404, detail="会话不存在")
            session.last_active_at = datetime.utcnow()
    else:
        # 匿名用户：使用临时会话 ID（基于 IP + 时间戳）
        import hashlib
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        session_id = f"anon_{hashlib.md5(f'{client_ip}:{ts}'.encode()).hexdigest()[:12]}"
    
    # 保存用户消息到数据库（匿名用户不保存）
    if not is_anonymous:
        user_message = Message(
            session_id=session_id,
            role="user",
            content=chat_req.message,
            agent_type="user"
        )
        db.add(user_message)
        await db.commit()
    
    # 流式生成回复
    async def generate():
        full_response = ""
        agent_type = "chat"
        
        async for msg in chat_agent.process(
            chat_req.message,
            session_id,
            force_tool="knowledge" if is_anonymous else (chat_req.command if chat_req.command else None),
            db=db
        ):
            msg_type = msg.get("type", "content")
            
            if msg_type == "routing":
                agent_type = msg.get("agent", "chat")
                yield f"event: routing\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
            
            elif msg_type == "tool_call":
                yield f"event: tool_call\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
            
            elif msg_type == "articles":
                yield f"event: articles\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
            
            elif msg_type == "info":
                yield f"event: info\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
            
            elif msg_type == "error":
                yield f"event: error\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
            
            elif msg_type == "options":
                yield f"event: options\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
            
            elif msg_type == "search_options":
                yield f"event: search_options\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
            
            elif msg_type == "knowledge_sources":
                yield f"event: knowledge_sources\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
            
            elif msg_type == "search_sources":
                yield f"event: search_sources\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
            
            elif msg_type == "react_action":
                yield f"event: react_action\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
            
            elif msg_type == "react_observation":
                yield f"event: react_observation\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"

            elif msg_type == "react_search_results":
                yield f"event: react_search_results\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"

            elif msg_type == "react_formatted":
                yield f"event: react_formatted\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"

            elif msg_type == "semantic_recall":
                yield f"event: semantic_recall\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"

            elif msg_type == "content":
                full_response += msg.get("content", "")
                yield f"data: {json.dumps({'content': msg.get('content', '')}, ensure_ascii=False)}\n\n"
            
            elif msg_type == "done":
                pass
        
        # 保存助手回复到数据库
        if not is_anonymous:
            assistant_message = Message(
                session_id=session_id,
                role="assistant",
                content=full_response,
                agent_type=agent_type,
                metadata_={"agent": agent_type}
            )
            db.add(assistant_message)
            await db.commit()

        # 保存到 Redis 短期记忆（所有 Agent 流统一在此写入）
        if not is_anonymous and session_id:
            from app.core.history_manager import history_manager
            await history_manager.save_message(session_id, "user", chat_req.message)
            await history_manager.save_message(session_id, "assistant", full_response)

        # 批次语义记忆：每 5 轮触发一次 embedding（匿名用户不触发）
        if not is_anonymous:
            try:
                from app.core.redis import get_redis
                redis = await get_redis()
                round_key = f"round_counter:{session_id}"
                round_count = await redis.incr(round_key)
                await redis.expire(round_key, 86400)  # 24h TTL

                if round_count % 5 == 0:
                    result = await db.execute(
                        select(Message.content)
                        .where(Message.session_id == session_id, Message.role == "user")
                        .order_by(Message.created_at.desc())
                        .limit(5)
                    )
                    user_messages = [row[0] for row in result.all()]
                    user_messages.reverse()

                    if user_messages:
                        batch_label = f"rounds-{round_count-4}-{round_count}"
                        user_text = "\n---\n".join(user_messages)
                        await history_manager.save_batch_memory(
                            session_id, batch_label, user_text, db
                        )
                        await db.commit()
            except Exception as e:
                logger.warning(f"批次语义记忆写入失败（不阻塞主流程）: {e}")

        # 发送完成信号
        yield f"event: done\ndata: {json.dumps({'done': True, 'session_id': session_id, 'agent': agent_type, 'is_anonymous': is_anonymous, 'daily_remaining': daily_remaining}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )


@router.get("/sessions")
async def get_sessions(token: str, db: AsyncSession = Depends(get_db)):
    """
    获取用户的会话列表
    
    Args:
        token: JWT Token
    
    Returns:
        list: 会话列表
    """
    # 验证 Token
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的 Token")
    
    result = await db.execute(
        select(Session)
        .where(Session.user_id == user_id, Session.deleted_at == None)
        .order_by(Session.updated_at.desc())
        .limit(20)
    )
    sessions = result.scalars().all()
    
    return [
        {
            "id": str(session.id),
            "title": session.title,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat()
        }
        for session in sessions
    ]


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, token: str, db: AsyncSession = Depends(get_db)):
    """
    获取会话的消息列表
    
    Args:
        session_id: 会话 ID
        token: JWT Token
    
    Returns:
        list: 消息列表
    """
    # 验证 Token
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的 Token")
    
    # 验证会话存在且属于当前用户
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.user_id == user_id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    # 查询消息
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id, Message.deleted_at == None)
        .order_by(Message.created_at.asc())
    )
    messages = result.scalars().all()
    
    return [
        {
            "id": str(message.id),
            "role": message.role,
            "content": message.content,
            "agent_type": message.agent_type,
            "created_at": message.created_at.isoformat()
        }
        for message in messages
    ]
