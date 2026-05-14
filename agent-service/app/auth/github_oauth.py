"""
GitHub OAuth 认证模块

负责：
- 生成 GitHub OAuth 授权 URL
- 处理 OAuth 回调
- 获取用户信息
"""
import httpx
from typing import Optional, Dict
from loguru import logger

from app.config import settings


# GitHub OAuth 端点
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_API = "https://api.github.com/user"


def get_authorize_url(state: str) -> str:
    """
    生成 GitHub OAuth 授权 URL
    
    Args:
        state: 随机状态参数，用于防止 CSRF 攻击
    
    Returns:
        str: 授权 URL
    """
    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.GITHUB_REDIRECT_URI,
        "scope": "read:user user:email",
        "state": state
    }
    
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    url = f"{GITHUB_AUTHORIZE_URL}?{query_string}"
    
    return url


async def exchange_code_for_token(code: str) -> Optional[str]:
    """
    用授权码换取访问 Token
    
    Args:
        code: GitHub 授权码
    
    Returns:
        Optional[str]: 访问 Token，失败返回 None
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                GITHUB_TOKEN_URL,
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code
                },
                headers={"Accept": "application/json"}
            )
            
            if response.status_code != 200:
                logger.error(f"获取 GitHub Token 失败: {response.text}")
                return None
            
            data = response.json()
            access_token = data.get("access_token")
            
            return access_token
            
        except Exception as e:
            logger.error(f"请求 GitHub Token 失败: {e}")
            return None


async def get_user_info(access_token: str) -> Optional[Dict]:
    """
    获取 GitHub 用户信息
    
    Args:
        access_token: GitHub 访问 Token
    
    Returns:
        Optional[Dict]: 用户信息字典，失败返回 None
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                GITHUB_USER_API,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json"
                }
            )
            
            if response.status_code != 200:
                logger.error(f"获取 GitHub 用户信息失败: {response.text}")
                return None
            
            data = response.json()
            
            # 提取需要的字段
            user_info = {
                "github_id": data.get("id"),
                "github_username": data.get("login"),
                "nickname": data.get("name") or data.get("login"),
                "email": data.get("email"),
                "avatar_url": data.get("avatar_url")
            }
            
            return user_info
            
        except Exception as e:
            logger.error(f"请求 GitHub 用户信息失败: {e}")
            return None
