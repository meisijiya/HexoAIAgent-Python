# RAG 知识库实现

> 📅 日期：2024-05-14
> 🏷️ 标签：RAG、Embedding、向量检索、分块策略

---

## 📖 概述

本文记录 RAG（Retrieval-Augmented Generation）知识库的实现过程，包括文档分块、向量化、检索等核心环节。

---

## 🎯 什么是 RAG

RAG = **R**etrieval（检索）+ **A**ugmented（增强）+ **G**eneration（生成）

```
用户问题
    ↓
检索相关文档（Retrieval）
    ↓
增强上下文（Augmented）
    ↓
生成回答（Generation）
```

### 核心思想

1. **先检索**：从知识库中找到相关文档
2. **再生成**：基于检索结果生成回答
3. **优势**：结合外部知识，减少幻觉

---

## 📄 文档分块

### 为什么需要分块

- LLM 有上下文长度限制
- 需要精确定位相关信息
- 提高检索效率

### 分块策略

```python
# 三阶段分块策略
def chunk_markdown(content: str) -> List[Dict]:
    """
    阶段 1: 按 Markdown 标题切分
    阶段 2: 按字符数二次分割
    阶段 3: 合并过小分片
    """
    
    # 阶段 1: 按标题切分
    sections = split_by_headers(content)
    
    # 阶段 2: 按字符数分割
    chunks = []
    for section in sections:
        if len(section) <= 500:
            chunks.append(section)
        else:
            chunks.extend(split_by_size(section, 500))
    
    # 阶段 3: 合并过小分片
    merged = merge_small_chunks(chunks, min_size=300)
    
    return merged
```

### 分块参数

| 参数 | 值 | 说明 |
|------|-----|------|
| min_chunk_size | 300 字符 | 最小分块大小 |
| max_chunk_size | 500 字符 | 最大分块大小 |
| chunk_overlap | 0 字符 | 重叠区域（当前无重叠）|

### 分块示例

```markdown
# Hexo 安装指南

## 前置条件

1. 安装 Node.js
2. 安装 Git

## 安装步骤

```bash
npm install -g hexo-cli
hexo init my-blog
```
```

分块结果：
```
Chunk 1: "# Hexo 安装指南\n\n## 前置条件\n\n1. 安装 Node.js\n2. 安装 Git"
Chunk 2: "## 安装步骤\n\n```bash\nnpm install -g hexo-cli\nhexo init my-blog\n```"
```

---

## 🔢 向量化（Embedding）

### 什么是 Embedding

将文本转换为高维向量，捕捉语义信息。

```
"如何安装 Hexo" → [0.1, 0.2, 0.3, ..., 0.9] (1024 维)
```

### 选择 Embedding 模型

| 模型 | 维度 | 价格 | 选择 |
|------|------|------|------|
| DashScope text-embedding-v4 | 1024 | ¥0.7/百万 tokens | ✅ |
| OpenAI text-embedding-3-small | 1536 | $0.02/百万 tokens | ❌ |
| BGE-M3 | 1024 | 免费（本地） | ❌ |

### 调用 DashScope API

```python
# app/knowledge/embedder.py
import httpx

class EmbeddingService:
    def __init__(self):
        self.api_key = settings.DASHSCOPE_API_KEY
        self.model = "text-embedding-v4"
        self.dimension = 1024
        self.api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
    
    async def embed_query(self, text: str) -> List[float]:
        """单条文本向量化"""
        return (await self.embed_batch([text]))[0]
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量向量化（自动分批，每批最多 10 条）"""
        all_embeddings = []
        
        for i in range(0, len(texts), 10):  # DashScope 限制每批 10 条
            batch = texts[i:i + 10]
            batch_embeddings = await self._call_api(batch)
            all_embeddings.extend(batch_embeddings)
        
        return all_embeddings
    
    async def _call_api(self, texts: List[str]) -> List[List[float]]:
        """调用 DashScope API"""
        async with httpx.AsyncClient() as client:
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
                }
            )
            
            data = response.json()
            return [item["embedding"] for item in data["data"]]
```

### 批量处理问题

**问题**：DashScope API 限制单次最多 10 条

**解决**：分批处理

```python
async def embed_batch(self, texts: List[str]) -> List[List[float]]:
    """批量向量化（自动分批）"""
    all_embeddings = []
    
    # 每批最多 10 条
    for i in range(0, len(texts), 10):
        batch = texts[i:i + 10]
        batch_embeddings = await self._call_api(batch)
        all_embeddings.extend(batch_embeddings)
    
    return all_embeddings
```

---

## 💾 向量存储

### pgvector 数据类型

```sql
-- 创建向量列
CREATE TABLE knowledge_chunks (
    id UUID PRIMARY KEY,
    content TEXT,
    embedding VECTOR(1024)  -- 1024 维向量
);

-- 创建向量索引
CREATE INDEX idx_chunks_vector ON knowledge_chunks 
    USING ivfflat (embedding vector_cosine_ops);
```

### 存储向量

```python
# 保存分块和向量
async def store_chunks(article_id: str, chunks: List[Dict]):
    for chunk in chunks:
        # 生成向量
        embedding = await embedding_service.embed_query(chunk["content"])
        
        # 保存到数据库
        db_chunk = Chunk(
            article_id=article_id,
            content=chunk["content"],
            embedding=embedding,
            metadata_=chunk["metadata"]
        )
        db.add(db_chunk)
    
    await db.commit()
```

---

## 🔍 向量检索

### 距离计算

pgvector 支持三种距离：

| 距离类型 | 运算符 | 说明 | 适用场景 |
|----------|--------|------|----------|
| 余弦距离 | `<=>` | cos(θ) | 文本相似度 |
| L2 距离 | `<->` | 欧氏距离 | 图像相似度 |
| 内积 | `<#>` | 点积 | 推荐系统 |

**我们使用余弦距离**：

```sql
-- 余弦距离搜索
SELECT 
    content,
    1 - (embedding <=> query_vector) AS similarity
FROM knowledge_chunks
ORDER BY embedding <=> query_vector
LIMIT 5;
```

### 检索实现

```python
# app/knowledge/retriever.py
from sqlalchemy import text

class Retriever:
    async def search(self, db: AsyncSession, query: str, top_k: int = 5):
        """向量检索"""
        
        # 1. 查询向量化
        query_embedding = await embedding_service.embed_query(query)
        
        # 2. 向量搜索
        sql = text("""
            SELECT 
                id,
                content,
                metadata,
                1 - (embedding <=> CAST(:query_embedding AS vector)) AS similarity
            FROM knowledge_chunks
            ORDER BY embedding <=> CAST(:query_embedding AS vector)
            LIMIT :top_k
        """)
        
        result = await db.execute(sql, {
            "query_embedding": str(query_embedding),
            "top_k": top_k
        })
        
        rows = result.fetchall()
        
        # 3. 过滤低分结果
        return [
            SearchResult(
                id=row.id,
                content=row.content,
                score=float(row.similarity),
                metadata=row.metadata
            )
            for row in rows
            if row.similarity > 0.3  # 相似度阈值
        ]
```

---

## 🤖 知识库 Agent

### 核心流程

```
用户查询
    ↓
向量检索（Top 3）
    ↓
构建上下文
    ↓
LLM 生成回答
```

### 实现代码

```python
# app/agents/knowledge_agent.py
class KnowledgeAgent:
    async def search_and_answer(self, query: str):
        # 1. 检索相关文档
        search_results = await retriever.search(db, query, top_k=3)
        
        # 2. 构建上下文
        context = self._build_context(search_results)
        
        # 3. 构建 Prompt
        messages = [
            {"role": "system", "content": KNOWLEDGE_PROMPT},
            {"role": "user", "content": f"参考资料：\n{context}\n\n用户问题：{query}"}
        ]
        
        # 4. 调用 LLM
        async for chunk in llm_client.chat_stream(messages):
            yield chunk
    
    def _build_context(self, results: List[SearchResult]) -> str:
        """构建检索上下文"""
        context_parts = []
        for i, result in enumerate(results, 1):
            source = result.metadata.get("_source", "未知来源")
            context_parts.append(f"[参考资料 {i}] (来源: {source})\n{result.content}")
        return "\n\n".join(context_parts)
```

### Prompt 设计

```python
KNOWLEDGE_PROMPT = """你是一个专业的知识库助手，专门根据提供的参考资料回答问题。

你的任务：
1. 仔细阅读参考资料
2. 基于参考资料回答用户问题
3. 如果参考资料中没有相关信息，诚实地说不知道
4. 回答要准确、简洁
5. 引用参考资料时注明来源

请用中文回复。"""
```

---

## 📊 测试效果

### 测试查询

| 查询 | 相似度 | 结果质量 |
|------|--------|----------|
| "Redis 分布式锁怎么实现" | 0.82 | ✅ 好 |
| "Mybatis-plus 如何配置" | 0.73 | ⭐ 一般 |
| "什么是 AI Agent" | 0.75 | ⭐ 一般 |

### 问题分析

1. **相似度阈值**：0.3 可能太低，返回不相关结果
2. **分块大小**：可能需要调整
3. **检索方式**：纯向量检索，可考虑混合检索

---

## 🎯 优化方向

### 1. 分块优化

- 增加分块大小（500 → 1000）
- 增加重叠区域（0 → 100）
- 按语义边界分块

### 2. 检索优化

- 动态相似度阈值
- 动态 Top K
- 混合检索（向量 + 关键词）

### 3. 生成优化

- Prompt 工程
- Few-shot 示例
- 思维链（CoT）

---

## 📝 总结

### 关键点

1. **分块策略**：三阶段分块，平衡大小和质量
2. **Embedding**：DashScope API，1024 维向量
3. **向量存储**：pgvector，PostgreSQL 扩展
4. **检索方式**：余弦距离，Top K

### 注意事项

1. **批量限制**：DashScope 每批最多 10 条
2. **相似度阈值**：需要根据场景调整
3. **分块大小**：影响检索精度

### 后续优化

1. **RAG 优化**：提升准确率
2. **混合检索**：向量 + 关键词
3. **重排序**：Cross-encoder

---

## 📚 参考资源

- [pgvector 文档](https://github.com/pgvector/pgvector)
- [DashScope API](https://dashscope.aliyuncs.com/)
- [RAG 论文](https://arxiv.org/abs/2005.11401)

---

**上一篇：[FastAPI 服务搭建](./02-FastAPI服务搭建.md)** ← → **下一篇：[Agent 调度器实现](./04-Agent调度器实现.md)** →
