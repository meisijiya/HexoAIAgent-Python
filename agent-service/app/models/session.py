"""
会话模型模块

存储用户与 Agent 的对话会话
"""
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Session(BaseModel):
    """
    会话模型
    
    每个会话代表一次对话上下文
    一个用户可以有多个会话
    """
    __tablename__ = "agent_sessions"
    
    # 关联用户
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_users.id", ondelete="CASCADE"),
        nullable=False,
        comment="用户 ID"
    )
    
    # 会话标题（自动生成或用户设置）
    title = Column(
        String(200),
        nullable=True,
        comment="会话标题"
    )
    
    # 关联关系
    user = relationship("User", backref="sessions")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Session(id={self.id}, title={self.title})>"
