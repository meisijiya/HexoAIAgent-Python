"""
对话 API 路由模块

提供对话相关接口，使用调度器协调多个 Agent
"""
import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from loguru import logger

from app.core.database import get_db
from app.core.redis import check_rate_limit
from app.agents.chat_agent import chat_agent
from app.models.user import User
from app.models.session import Session
from app.models.message import Message
from app.auth.token import verify_token

router = APIRouter(prefix="/api/chat", tags=["对话"])


class ChatRequest(BaseModel):
    """对话请求模型"""
    message: str
    session_id: Optional[str] = None
    command: Optional[str] = None
    token: str


@router.post("")
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """
    对话接口（流式输出）
    
    ChatAgent 作为唯一入口，LLM 判断意图后路由到对应子 Agent
    
    Args:
        request: 对话请求
    
    Returns:
        StreamingResponse: 流式响应
    """
    # 验证 Token
    user_id = verify_token(request.token)
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的 Token")
    
    # 检查限流
    if not await check_rate_limit(user_id):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    
    # 获取或创建会话
    session_id = request.session_id
    
    if not session_id:
        # 创建新会话
        session = Session(
            user_id=user_id,
            title=request.message[:50] + "..." if len(request.message) > 50 else request.message
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
    
    # 保存用户消息到数据库
    user_message = Message(
        session_id=session_id,
        role="user",
        content=request.message,
        agent_type="user"
    )
    db.add(user_message)
    await db.commit()
    
    # 流式生成回复
    async def generate():
        full_response = ""
        agent_type = "chat"
        
        async for msg in chat_agent.process(
            request.message,
            session_id,
            force_tool=request.command if request.command else None,
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
        from app.core.history_manager import history_manager
        await history_manager.save_message(session_id, "user", request.message)
        await history_manager.save_message(session_id, "assistant", full_response)

        # 批次语义记忆：每 5 轮触发一次 embedding
        try:
            from app.core.redis import get_redis
            redis = await get_redis()
            round_key = f"round_counter:{session_id}"
            round_count = await redis.incr(round_key)
            await redis.expire(round_key, 86400)  # 24h TTL

            if round_count % 5 == 0:
                # 查询最近 5 条用户消息
                result = await db.execute(
                    select(Message.content)
                    .where(Message.session_id == session_id, Message.role == "user")
                    .order_by(Message.created_at.desc())
                    .limit(5)
                )
                user_messages = [row[0] for row in result.all()]
                user_messages.reverse()  # 时间正序

                if user_messages:
                    batch_label = f"rounds-{round_count-4}-{round_count}"
                    user_text = "\n---\n".join(user_messages)
                    await history_manager.save_batch_memory(
                        session_id, batch_label, user_text, db
                    )
                    await db.commit()  # 提交批次写入事务
        except Exception as e:
            logger.warning(f"批次语义记忆写入失败（不阻塞主流程）: {e}")

        # 发送完成信号
        yield f"event: done\ndata: {json.dumps({'done': True, 'session_id': session_id, 'agent': agent_type}, ensure_ascii=False)}\n\n"
    
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
    
    # 查询会话
    result = await db.execute(
        select(Session)
        .where(Session.user_id == user_id)
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
        .where(Message.session_id == session_id)
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
