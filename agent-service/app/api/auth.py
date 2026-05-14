"""
认证 API 路由模块

提供 GitHub OAuth 登录相关接口
"""
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.core.database import get_db
from app.core.redis import cache_oauth_state, get_oauth_state
from app.models.user import User
from app.auth.github_oauth import get_authorize_url, exchange_code_for_token, get_user_info
from app.auth.token import create_access_token, verify_token

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.get("/github")
async def github_login():
    """
    发起 GitHub OAuth 登录
    
    Returns:
        RedirectResponse: 重定向到 GitHub 授权页面
    """
    # 生成随机 state
    state = str(uuid.uuid4())
    
    # 缓存 state（10 分钟过期）
    await cache_oauth_state(state, "/")
    
    # 获取授权 URL
    authorize_url = get_authorize_url(state)
    
    return {"authorize_url": authorize_url}


@router.get("/github/callback")
async def github_callback(code: str, state: str, db: AsyncSession = Depends(get_db)):
    """
    GitHub OAuth 回调处理
    
    Args:
        code: 授权码
        state: 状态参数
    
    Returns:
        dict: 包含 token 和用户信息
    """
    # 验证 state
    cached_state = await get_oauth_state(state)
    if not cached_state:
        raise HTTPException(status_code=400, detail="无效的 state 参数")
    
    # 用授权码换取 Token
    github_token = await exchange_code_for_token(code)
    if not github_token:
        raise HTTPException(status_code=400, detail="获取 GitHub Token 失败")
    
    # 获取用户信息
    user_info = await get_user_info(github_token)
    if not user_info:
        raise HTTPException(status_code=400, detail="获取用户信息失败")
    
    # 查找或创建用户
    result = await db.execute(
        select(User).where(User.github_id == user_info["github_id"])
    )
    user = result.scalar_one_or_none()
    
    if user:
        # 更新用户信息
        user.github_username = user_info["github_username"]
        user.nickname = user_info["nickname"]
        user.email = user_info["email"]
        user.avatar_url = user_info["avatar_url"]
        user.last_active_at = datetime.utcnow()
        logger.info(f"用户登录: {user.nickname}")
    else:
        # 创建新用户
        user = User(
            github_id=user_info["github_id"],
            github_username=user_info["github_username"],
            nickname=user_info["nickname"],
            email=user_info["email"],
            avatar_url=user_info["avatar_url"],
            is_anonymous=False,
            last_active_at=datetime.utcnow()
        )
        db.add(user)
        logger.info(f"新用户注册: {user_info['nickname']}")
    
    await db.commit()
    
    # 生成 JWT Token
    token = create_access_token(str(user.id))
    
    return {
        "token": token,
        "user": {
            "id": str(user.id),
            "nickname": user.nickname,
            "avatar_url": user.avatar_url
        }
    }


@router.get("/me")
async def get_current_user(token: str, db: AsyncSession = Depends(get_db)):
    """
    获取当前用户信息
    
    Args:
        token: JWT Token
    
    Returns:
        dict: 用户信息
    """
    # 验证 Token
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的 Token")
    
    # 查询用户
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    return {
        "id": str(user.id),
        "nickname": user.nickname,
        "email": user.email,
        "avatar_url": user.avatar_url,
        "is_anonymous": user.is_anonymous
    }


@router.post("/anonymous")
async def create_anonymous_user(db: AsyncSession = Depends(get_db)):
    """
    创建匿名用户
    
    Returns:
        dict: 包含 token 和用户信息
    """
    # 创建匿名用户
    user = User(
        nickname=f"匿名用户_{uuid.uuid4().hex[:8]}",
        is_anonymous=True,
        last_active_at=datetime.utcnow()
    )
    db.add(user)
    await db.commit()
    
    # 生成 Token
    token = create_access_token(str(user.id))
    
    logger.info(f"匿名用户创建: {user.id}")
    
    return {
        "token": token,
        "user": {
            "id": str(user.id),
            "nickname": user.nickname,
            "avatar_url": None
        }
    }
