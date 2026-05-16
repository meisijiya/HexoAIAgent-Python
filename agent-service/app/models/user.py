"""
用户模型模块

存储用户信息，支持 GitHub OAuth 登录和匿名用户
"""
from sqlalchemy import Column, String, BigInteger, Boolean, DateTime, Enum
from app.models.base import BaseModel
import enum


class UserRole(str, enum.Enum):
    """用户角色枚举"""
    USER = "user"       # 普通用户
    ADMIN = "admin"     # 管理员
    BANNED = "banned"   # 已封禁


class User(BaseModel):
    """
    用户模型
    
    支持两种用户类型：
    1. 匿名用户：自动生成 UUID，无需登录
    2. GitHub 用户：通过 OAuth 登录，绑定 GitHub 账号
    """
    __tablename__ = "agent_users"
    
    # GitHub OAuth 相关
    github_id = Column(
        BigInteger,
        unique=True,
        nullable=True,
        comment="GitHub 用户 ID"
    )
    
    github_username = Column(
        String(100),
        nullable=True,
        comment="GitHub 用户名"
    )
    
    # 用户基本信息
    nickname = Column(
        String(50),
        nullable=True,
        comment="昵称"
    )
    
    email = Column(
        String(100),
        nullable=True,
        comment="邮箱"
    )
    
    avatar_url = Column(
        String(255),
        nullable=True,
        comment="头像 URL"
    )
    
    # 用户状态
    is_anonymous = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="是否匿名用户"
    )
    
    last_active_at = Column(
        DateTime,
        nullable=True,
        comment="最后活跃时间"
    )
    
    # 角色（用于后台管理权限控制）
    role = Column(
        String(20),
        default=UserRole.USER,
        nullable=False,
        comment="用户角色: user / admin / banned"
    )
    
    # 账号状态（封禁/停用时设为 False）
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="账号是否激活"
    )
    
    def __repr__(self):
        return f"<User(id={self.id}, nickname={self.nickname}, is_anonymous={self.is_anonymous})>"
