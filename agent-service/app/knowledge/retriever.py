"""
向量检索模块

负责：
- 将查询文本向量化
- 在 PostgreSQL 中进行相似度搜索
- 返回最相关的文档片段
"""
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from loguru import logger

from app.knowledge.embedder import embedding_service


class SearchResult:
    """搜索结果类"""
    
    def __init__(self, id: str, content: str, score: float, metadata: Dict[str, Any]):
        self.id = id
        self.content = content
        self.score = score
        self.metadata = metadata
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "score": self.score,
            "metadata": self.metadata
        }


class Retriever:
    """
    向量检索器
    
    使用 pgvector 进行相似度搜索
    """
    
    async def search(
        self,
        db: AsyncSession,
        query: str,
        top_k: int = 5
    ) -> List[SearchResult]:
        """
        搜索与查询最相关的文档片段
        
        Args:
            db: 数据库会话
            query: 查询文本
            top_k: 返回结果数量
        
        Returns:
            List[SearchResult]: 搜索结果列表
        """
        # 查询文本向量化
        query_embedding = await embedding_service.embed_query(query)
        
        # pgvector 相似度搜索（使用余弦距离）
        sql = text("""
            SELECT 
                id::text,
                content,
                metadata,
                1 - (embedding <=> :query_embedding::vector) as similarity
            FROM knowledge_chunks
            ORDER BY embedding <=> :query_embedding::vector
            LIMIT :top_k
        """)
        
        result = await db.execute(sql, {
            "query_embedding": str(query_embedding),
            "top_k": top_k
        })
        
        rows = result.fetchall()
        
        # 构建搜索结果
        search_results = []
        for row in rows:
            if row.similarity > 0.3:  # 相似度阈值
                search_results.append(SearchResult(
                    id=row.id,
                    content=row.content,
                    score=float(row.similarity),
                    metadata=row.metadata or {}
                ))
        
        logger.info(f"知识库检索: '{query[:30]}...', 找到 {len(search_results)} 条结果")
        
        return search_results


# 全局检索器实例
retriever = Retriever()
