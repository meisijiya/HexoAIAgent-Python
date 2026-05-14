"""
向量检索模块（优化版）

负责：
- 将查询文本向量化
- 在 PostgreSQL 中进行相似度搜索
- 支持动态相似度阈值
- 支持动态 Top K
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
    向量检索器（优化版）
    
    使用 pgvector 进行相似度搜索，支持：
    - 动态相似度阈值
    - 动态 Top K
    """
    
    # 相似度阈值配置
    SIMILARITY_THRESHOLDS = {
        "high": 0.7,    # 高置信度
        "medium": 0.5,  # 中等置信度
        "low": 0.3,     # 低置信度
    }
    
    # Top K 配置
    TOP_K_CONFIG = {
        "simple": 2,     # 简单问题
        "medium": 3,     # 中等问题
        "complex": 5,    # 复杂问题
    }
    
    async def search(
        self,
        db: AsyncSession,
        query: str,
        top_k: int = None,
        threshold: float = None,
        dynamic: bool = True
    ) -> List[SearchResult]:
        """
        搜索与查询最相关的文档片段
        
        Args:
            db: 数据库会话
            query: 查询文本
            top_k: 返回结果数量（如果 dynamic=True，会自动调整）
            threshold: 相似度阈值（如果 dynamic=True，会自动调整）
            dynamic: 是否启用动态调整
        
        Returns:
            List[SearchResult]: 搜索结果列表
        """
        
        # 动态调整参数
        if dynamic:
            if top_k is None:
                top_k = self._get_dynamic_top_k(query)
            if threshold is None:
                threshold = self._get_dynamic_threshold(query)
        else:
            top_k = top_k or 3
            threshold = threshold or 0.3
        
        # 查询文本向量化
        query_embedding = await embedding_service.embed_query(query)
        
        # pgvector 相似度搜索（使用余弦距离）
        sql = text("""
            SELECT 
                CAST(id AS TEXT) as id,
                content,
                metadata,
                1 - (embedding <=> CAST(:query_embedding AS vector)) as similarity
            FROM knowledge_chunks
            WHERE 1 - (embedding <=> CAST(:query_embedding AS vector)) > :threshold
            ORDER BY embedding <=> CAST(:query_embedding AS vector)
            LIMIT :top_k
        """)
        
        result = await db.execute(sql, {
            "query_embedding": str(query_embedding),
            "threshold": threshold,
            "top_k": top_k
        })
        
        rows = result.fetchall()
        
        # 构建搜索结果
        search_results = []
        for row in rows:
            search_results.append(SearchResult(
                id=row.id,
                content=row.content,
                score=float(row.similarity),
                metadata=row.metadata or {}
            ))
        
        logger.info(f"知识库检索: '{query[:30]}...', 阈值: {threshold}, Top K: {top_k}, 找到 {len(search_results)} 条结果")
        
        # 如果结果不足，尝试降低阈值
        if len(search_results) < 2 and dynamic:
            logger.info(f"结果不足，降低阈值重新检索")
            return await self.search(db, query, top_k, threshold=0.3, dynamic=False)
        
        return search_results
    
    def _get_dynamic_threshold(self, query: str) -> float:
        """
        获取动态相似度阈值
        
        策略：
        1. 先用高阈值
        2. 如果查询复杂，降低阈值
        """
        
        # 分析查询复杂度
        complexity = self._analyze_query_complexity(query)
        
        # 根据复杂度选择阈值
        if complexity == "simple":
            return self.SIMILARITY_THRESHOLDS["high"]  # 0.7
        elif complexity == "medium":
            return self.SIMILARITY_THRESHOLDS["medium"]  # 0.5
        else:
            return self.SIMILARITY_THRESHOLDS["low"]  # 0.3
    
    def _get_dynamic_top_k(self, query: str) -> int:
        """
        获取动态 Top K
        
        策略：
        1. 简单问题少返回
        2. 复杂问题多返回
        """
        
        # 分析查询复杂度
        complexity = self._analyze_query_complexity(query)
        
        # 根据复杂度选择 Top K
        return self.TOP_K_CONFIG.get(complexity, 3)
    
    def _analyze_query_complexity(self, query: str) -> str:
        """
        分析查询复杂度
        
        简单：单一概念，如 "什么是 Redis"
        中等：具体问题，如 "Redis 怎么实现分布式锁"
        复杂：多步骤，如 "如何设计一个高并发的秒杀系统"
        """
        
        # 关键词数量
        keywords = len(query.split())
        
        # 问号数量
        question_marks = query.count("?") + query.count("？")
        
        # 连接词
        connectors = ["并且", "同时", "然后", "接着", "首先", "其次", "对比", "比较"]
        has_connectors = any(c in query for c in connectors)
        
        # 疑问词
        question_words = ["怎么", "如何", "为什么", "是什么", "哪些", "怎样"]
        has_question_words = any(w in query for w in question_words)
        
        if keywords <= 4 and question_marks <= 1 and not has_connectors:
            return "simple"
        elif keywords <= 10 and not has_connectors:
            return "medium"
        else:
            return "complex"


# 全局检索器实例
retriever = Retriever()
