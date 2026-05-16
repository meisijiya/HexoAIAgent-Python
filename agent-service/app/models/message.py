"""
消息模型模块

存储对话消息，包括用户输入和 Agent 回复
"""
from sqlalchemy import Column, String, Text, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Message(BaseModel):
    """
    消息模型
    
    存储每一条对话消息
    支持多种 Agent 类型的回复
    """
    __tablename__ = "agent_messages"
    
    # 关联会话
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        comment="会话 ID"
    )
    
    # 消息角色：user / assistant
    role = Column(
        String(20),
        nullable=False,
        comment="消息角色"
    )
    
    # 消息内容
    content = Column(
        Text,
        nullable=False,
        comment="消息内容"
    )
    
    # Agent 类型：chat / knowledge / search
    agent_type = Column(
        String(20),
        nullable=True,
        comment="Agent 类型"
    )
    
    # 扩展数据（检索来源、token 消耗等）
    metadata_ = Column(
        "metadata",
        JSONB,
        nullable=True,
        comment="扩展数据"
    )
    
    # 软删除时间
    deleted_at = Column(
        DateTime,
        nullable=True,
        default=None,
        comment="软删除时间"
    )
    
    # 关联关系
    session = relationship("Session", back_populates="messages")
    
    def __repr__(self):
        return f"<Message(id={self.id}, role={self.role}, agent_type={self.agent_type})>"
