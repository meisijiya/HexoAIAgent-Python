"""
Embedding 服务模块（优化版）

负责：
- 调用 DashScope API 生成文本向量
- 支持单条和批量向量化
- 自动分批处理（DashScope 限制每批最多 10 条）
- 支持缓存机制（避免重复调用 API）
"""
from typing import List, Dict
import hashlib
import json
from loguru import logger

from app.config import settings
from app.core.redis import get_redis


# DashScope API 单次最大处理数量
MAX_BATCH_SIZE = 10

# 缓存过期时间（秒）
CACHE_TTL = 86400 * 7  # 7 天


class EmbeddingService:
    """
    Embedding 服务（优化版）
    
    改进点：
    1. 支持 Redis 缓存
    2. 避免重复调用 API
    3. 提升响应速度
    """
    
    def __init__(self):
        """初始化 Embedding 服务"""
        self.api_key = settings.DASHSCOPE_API_KEY
        self.model = settings.EMBEDDING_MODEL
        self.dimension = settings.EMBEDDING_DIMENSION
        self.api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
        self._cache = {}  # 本地缓存（进程级）
    
    def _get_cache_key(self, text: str) -> str:
        """
        生成缓存键
        
        Args:
            text: 文本内容
        
        Returns:
            str: 缓存键
        """
        # 使用文本的 hash 作为缓存键
        return f"embedding:{hashlib.md5(text.encode()).hexdigest()}"
    
    async def _get_from_cache(self, text: str) -> List[float]:
        """
        从缓存获取向量
        
        Args:
            text: 文本内容
        
        Returns:
            List[float]: 向量（如果缓存命中）
        """
        cache_key = self._get_cache_key(text)
        
        # 1. 先检查本地缓存
        if cache_key in self._cache:
            logger.debug(f"本地缓存命中: {text[:20]}...")
            return self._cache[cache_key]
        
        # 2. 检查 Redis 缓存
        try:
            redis_client = await get_redis()
            cached = await redis_client.get(cache_key)
            
            if cached:
                embedding = json.loads(cached)
                # 存入本地缓存
                self._cache[cache_key] = embedding
                logger.debug(f"Redis 缓存命中: {text[:20]}...")
                return embedding
        except Exception as e:
            logger.warning(f"Redis 缓存读取失败: {e}")
        
        return None
    
    async def _set_cache(self, text: str, embedding: List[float]):
        """
        设置缓存
        
        Args:
            text: 文本内容
            embedding: 向量
        """
        cache_key = self._get_cache_key(text)
        
        # 1. 存入本地缓存
        self._cache[cache_key] = embedding
        
        # 2. 存入 Redis 缓存
        try:
            redis_client = await get_redis()
            await redis_client.setex(
                cache_key,
                CACHE_TTL,
                json.dumps(embedding)
            )
        except Exception as e:
            logger.warning(f"Redis 缓存写入失败: {e}")
    
    async def embed_query(self, text: str) -> List[float]:
        """
        将单条文本转换为向量（带缓存）
        
        Args:
            text: 要向量化的文本
        
        Returns:
            List[float]: 向量（1024 维）
        """
        # 检查缓存
        cached = await self._get_from_cache(text)
        if cached:
            return cached
        
        # 调用 API
        embedding = (await self._embed_batch_internal([text]))[0]
        
        # 存入缓存
        await self._set_cache(text, embedding)
        
        return embedding
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量将文本转换为向量（带缓存）
        
        Args:
            texts: 文本列表
        
        Returns:
            List[List[float]]: 向量列表
        """
        if not texts:
            return []
        
        # 检查缓存
        results = [None] * len(texts)
        texts_to_embed = []
        indices_to_embed = []
        
        for i, text in enumerate(texts):
            cached = await self._get_from_cache(text)
            if cached:
                results[i] = cached
            else:
                texts_to_embed.append(text)
                indices_to_embed.append(i)
        
        # 如果所有文本都有缓存，直接返回
        if not texts_to_embed:
            return results
        
        # 调用 API 处理未缓存的文本
        embeddings = []
        for i in range(0, len(texts_to_embed), MAX_BATCH_SIZE):
            batch = texts_to_embed[i:i + MAX_BATCH_SIZE]
            batch_embeddings = await self._embed_batch_internal(batch)
            embeddings.extend(batch_embeddings)
        
        # 存入缓存并填充结果
        for i, (text, embedding) in enumerate(zip(texts_to_embed, embeddings)):
            await self._set_cache(text, embedding)
            results[indices_to_embed[i]] = embedding
        
        return results
    
    async def _embed_batch_internal(self, texts: List[str]) -> List[List[float]]:
        """
        内部方法：处理单批次的 Embedding 请求
        """
        import httpx
        
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
                
                if "error" in data:
                    logger.error(f"Embedding API 错误: {data['error']}")
                    raise Exception(f"Embedding API 错误: {data['error']['message']}")
                
                embeddings = sorted(data["data"], key=lambda x: x["index"])
                return [item["embedding"] for item in embeddings]
                
            except Exception as e:
                logger.error(f"Embedding 调用失败: {e}")
                raise
    
    async def get_cache_stats(self) -> Dict:
        """
        获取缓存统计信息
        
        Returns:
            Dict: 缓存统计
        """
        local_cache_size = len(self._cache)
        
        try:
            redis_client = await get_redis()
            redis_cache_size = await redis_client.dbsize()
        except:
            redis_cache_size = -1
        
        return {
            "local_cache_size": local_cache_size,
            "redis_cache_size": redis_cache_size
        }


# 全局 Embedding 服务实例
embedding_service = EmbeddingService()
