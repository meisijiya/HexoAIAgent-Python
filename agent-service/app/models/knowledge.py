"""
知识库模型模块

存储博客文章、文章分块和向量数据
"""
from sqlalchemy import Column, String, Text, Integer, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from app.config import settings


class Article(BaseModel):
    """
    知识库文章模型
    
    存储原始博客文章
    """
    __tablename__ = "knowledge_articles"
    
    # 文章标题
    title = Column(
        String(200),
        nullable=False,
        comment="文章标题"
    )
    
    # 文章 URL（唯一）
    url = Column(
        String(500),
        unique=True,
        nullable=True,
        comment="文章 URL"
    )
    
    # 文章内容
    content = Column(
        Text,
        nullable=True,
        comment="文章内容"
    )
    
    # 来源：blog / manual
    source = Column(
        String(20),
        default="blog",
        comment="来源类型"
    )
    
    # 同步时间
    synced_at = Column(
        DateTime,
        nullable=True,
        comment="最后同步时间"
    )
    
    # 关联关系
    chunks = relationship("Chunk", back_populates="article", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Article(id={self.id}, title={self.title})>"


class Chunk(BaseModel):
    """
    文章分块模型
    
    存储文章的分块内容和向量
    用于 RAG 检索
    """
    __tablename__ = "knowledge_chunks"
    
    # 关联文章
    article_id = Column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_articles.id", ondelete="CASCADE"),
        nullable=False,
        comment="文章 ID"
    )
    
    # 分块索引
    chunk_index = Column(
        Integer,
        nullable=False,
        comment="分块索引"
    )
    
    # 分块内容
    content = Column(
        Text,
        nullable=False,
        comment="分块内容"
    )
    
    # 向量嵌入（1024 维）
    embedding = Column(
        Vector(settings.EMBEDDING_DIMENSION),
        nullable=True,
        comment="向量嵌入"
    )
    
    # 扩展数据
    metadata_ = Column(
        "metadata",
        JSONB,
        nullable=True,
        comment="扩展数据"
    )
    
    # 关联关系
    article = relationship("Article", back_populates="chunks")
    
    def __repr__(self):
        return f"<Chunk(id={self.id}, article_id={self.article_id}, index={self.chunk_index})>"


class SyncLog(BaseModel):
    """
    同步日志模型
    
    记录知识库同步的历史
    """
    __tablename__ = "knowledge_sync_logs"
    
    # 触发类型：github_action / manual
    trigger_type = Column(
        String(20),
        nullable=True,
        comment="触发类型"
    )
    
    # 状态：pending / running / success / failed
    status = Column(
        String(20),
        nullable=True,
        comment="同步状态"
    )
    
    # 文章数量
    articles_count = Column(
        Integer,
        default=0,
        comment="处理文章数"
    )
    
    # 错误信息
    error_message = Column(
        Text,
        nullable=True,
        comment="错误信息"
    )
    
    # 完成时间
    completed_at = Column(
        DateTime,
        nullable=True,
        comment="完成时间"
    )
    
    def __repr__(self):
        return f"<SyncLog(id={self.id}, status={self.status})>"
