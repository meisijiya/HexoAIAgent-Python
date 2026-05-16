"""
对话历史向量表模型

用于存储对话历史的 embedding，支持语义检索
"""
from sqlalchemy import Column, String, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import JSON
from datetime import datetime
import uuid

from app.models.base import Base


class ConversationMemory(Base):
    """
    对话历史向量表
    
    存储每轮对话的 embedding，用于语义检索召回旧历史
    """
    __tablename__ = "conversation_memories"
    
    # 主键
    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="记忆 ID (UUID)"
    )
    
    # 会话关联
    session_id = Column(
        String(36),
        nullable=False,
        index=True,
        comment="会话 ID"
    )
    
    # 角色
    role = Column(
        String(20),
        nullable=False,
        comment="角色 (user/assistant)"
    )
    
    # 对话内容（原文，用于展示和对比）
    content = Column(
        Text,
        nullable=False,
        comment="对话内容"
    )
    
    # embedding 向量（JSON 存储，与 DashScope text-embedding-v4 对齐）
    embedding = Column(
        JSON,
        nullable=True,
        comment="向量 embedding (1024 维)"
    )
    
    # 元数据（可扩展）
    # 使用 metadata_ 避免与 SQLAlchemy 保留字 metadata 冲突
    metadata_ = Column(
        "metadata",
        JSON,
        nullable=True,
        comment="附加元数据"
    )
    
    # 时间戳
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="创建时间"
    )
    
    # 软删除时间
    deleted_at = Column(
        DateTime,
        nullable=True,
        default=None,
        comment="软删除时间"
    )
    
    # 索引定义
    __table_args__ = (
        Index('ix_conversation_memories_session_created', 'session_id', 'created_at'),
    )
    
    def __repr__(self):
        return f"<ConversationMemory(id={self.id}, session_id={self.session_id}, role={self.role})>"