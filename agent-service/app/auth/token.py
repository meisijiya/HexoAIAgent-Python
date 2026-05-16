"""
JWT Token 管理模块

负责：
- 生成 JWT Token
- 验证 JWT Token
- 提取用户信息
"""
from datetime import datetime, timedelta
from typing import Optional
import jwt
from loguru import logger

from app.config import settings


def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建访问 Token
    
    Args:
        user_id: 用户 ID
        expires_delta: 过期时间增量
    
    Returns:
        str: JWT Token
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.utcnow()
    }
    
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    
    return token


def verify_token(token: str) -> Optional[str]:
    """
    验证 Token 并提取用户 ID
    
    Args:
        token: JWT Token
    
    Returns:
        Optional[str]: 用户 ID，验证失败返回 None
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        
        if user_id is None:
            return None
        
        return user_id
        
    except jwt.ExpiredSignatureError:
        logger.warning("Token 已过期")
        return None
    except jwt.PyJWTError as e:
        logger.warning(f"Token 验证失败: {e}")
        return None
