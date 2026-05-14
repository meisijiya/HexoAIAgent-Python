"""
搜索 API 路由模块

提供外部搜索相关接口
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from loguru import logger
import json

from app.core.redis import check_rate_limit
from app.agents.search_agent import search_agent
from app.auth.token import verify_token

router = APIRouter(prefix="/api/search", tags=["搜索"])


class SearchRequest(BaseModel):
    """搜索请求模型"""
    query: str
    token: str


@router.post("")
async def search(request: SearchRequest):
    """
    搜索接口（流式输出）
    
    Args:
        request: 搜索请求
    
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
    
    async def generate():
        async for chunk in search_agent.search_and_answer(request.query):
            yield f"data: {json.dumps({'content': chunk})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )
