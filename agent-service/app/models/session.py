"""
会话模型模块

存储用户与 Agent 的对话会话
"""
from sqlalchemy import Column, String, ForeignKey, DateTime
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
    
    # 最后活跃时间（由 chat handler 在每次发消息时更新，用于判断过期会话）
    last_active_at = Column(
        DateTime,
        nullable=True,
        default=None,
        comment="最后活跃时间"
    )
    
    # 软删除时间（清除会话时标记，定时任务据此物理清理旧记录）
    deleted_at = Column(
        DateTime,
        nullable=True,
        default=None,
        comment="软删除时间"
    )
    
    # 关联关系
    user = relationship("User", backref="sessions")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Session(id={self.id}, title={self.title})>"
