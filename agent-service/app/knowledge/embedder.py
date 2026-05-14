"""
Embedding 服务模块

负责：
- 调用 DashScope API 生成文本向量
- 支持单条和批量向量化
"""
from typing import List
import httpx
from loguru import logger

from app.config import settings


class EmbeddingService:
    """
    Embedding 服务
    
    使用 DashScope 的 text-embedding-v4 模型生成文本向量
    """
    
    def __init__(self):
        """初始化 Embedding 服务"""
        self.api_key = settings.DASHSCOPE_API_KEY
        self.model = settings.EMBEDDING_MODEL
        self.dimension = settings.EMBEDDING_DIMENSION
        self.api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
    
    async def embed_query(self, text: str) -> List[float]:
        """
        将单条文本转换为向量
        
        Args:
            text: 要向量化的文本
        
        Returns:
            List[float]: 向量（1024 维）
        """
        return (await self.embed_batch([text]))[0]
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量将文本转换为向量
        
        Args:
            texts: 文本列表
        
        Returns:
            List[List[float]]: 向量列表
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.api_url,
                    json={
                        "model": self.model,
                        "input": texts,
                        "dimensions": self.dimension
                    },
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    logger.error(f"Embedding API 调用失败: {response.text}")
                    raise Exception(f"Embedding API 返回 {response.status_code}")
                
                data = response.json()
                
                # 提取向量并按索引排序
                embeddings = sorted(data["data"], key=lambda x: x["index"])
                return [item["embedding"] for item in embeddings]
                
            except Exception as e:
                logger.error(f"Embedding 调用失败: {e}")
                raise


# 全局 Embedding 服务实例
embedding_service = EmbeddingService()
