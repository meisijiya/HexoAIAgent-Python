# FastAPI 服务搭建

> 📅 日期：2024-05-14
> 🏷️ 标签：FastAPI、Docker、PostgreSQL、Redis

---

## 📖 概述

本文记录如何从零搭建 FastAPI 服务，包括项目结构、数据库配置、Docker 部署等。

---

## 🚀 项目初始化

### 1. 创建项目结构

```bash
mkdir agent-service
cd agent-service

# 创建目录结构
mkdir -p app/{agents,core,knowledge,auth,api,models,utils}
touch app/__init__.py
```

### 2. 安装依赖

```txt
# requirements.txt
fastapi==0.109.0
uvicorn[standard]==0.27.0
sqlalchemy[asyncio]==2.0.25
asyncpg==0.29.0
pgvector==0.2.4
redis==5.0.1
pyjwt==2.8.0
httpx==0.26.0
openai==1.12.0
loguru==0.7.2
```

### 3. 配置管理

```python
# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # 数据库
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/hexo_agent"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # JWT
    SECRET_KEY: str = "your-secret-key"
    
    # LLM
    DEEPSEEK_API_KEY: str = ""
    
    # Embedding
    DASHSCOPE_API_KEY: str = ""
    
    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 🐘 数据库配置

### 1. SQLAlchemy 连接

```python
# app/core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# 创建引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=5,
    max_overflow=10
)

# 创建会话工厂
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

# 基类
class Base(DeclarativeBase):
    pass

# 依赖注入
async def get_db():
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### 2. 数据模型

```python
# app/models/user.py
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.core.database import Base

class User(Base):
    __tablename__ = "agent_users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nickname = Column(String(50))
    is_anonymous = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

### 3. pgvector 向量表

```python
# app/models/knowledge.py
from sqlalchemy import Column, String, Text, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector

class Chunk(Base):
    __tablename__ = "knowledge_chunks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    article_id = Column(UUID, ForeignKey("knowledge_articles.id"))
    content = Column(Text)
    embedding = Column(Vector(1024))  # 1024 维向量
    metadata_ = Column("metadata", JSONB)
```

---

## 🔴 Redis 配置

```python
# app/core/redis.py
import redis.asyncio as redis

# 连接池
redis_pool = None

async def init_redis():
    global redis_pool
    redis_pool = redis.from_url(settings.REDIS_URL, decode_responses=True)

async def get_redis():
    return redis_pool

# 会话上下文管理
async def get_session_context(session_id: str):
    redis_client = await get_redis()
    key = f"session:{session_id}:context"
    messages = await redis_client.lrange(key, 0, -1)
    return [json.loads(msg) for msg in messages]

async def add_message_to_context(session_id: str, role: str, content: str):
    redis_client = await get_redis()
    key = f"session:{session_id}:context"
    message = json.dumps({"role": role, "content": content})
    await redis_client.lpush(key, message)
    await redis_client.ltrim(key, 0, 19)  # 保留最近 20 条
    await redis_client.expire(key, 86400)  # 24 小时过期
```

---

## 🐳 Docker 部署

### 1. Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 2. docker-compose.yml

```yaml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: hexo_agent
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  agent-service:
    build: ./agent-service
    ports:
      - "8001:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:password@postgres:5432/hexo_agent
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - postgres
      - redis

volumes:
  postgres_data:
```

### 3. 启动命令

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f agent-service

# 停止服务
docker-compose down
```

---

## 📡 API 设计

### 1. 对话 API

```python
# app/api/chat.py
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/chat")

@router.post("")
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """流式对话接口"""
    
    async def generate():
        async for chunk in orchestrator.process(request.message, session_id):
            yield f"data: {json.dumps({'content': chunk})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")
```

### 2. 知识库 API

```python
# app/api/knowledge.py
@router.post("/articles")
async def create_article(article: ArticleCreate, db = Depends(get_db)):
    """创建文章"""
    # 1. 保存文章
    # 2. 分块
    # 3. 向量化
    # 4. 存储向量
    pass

@router.post("/search")
async def search_knowledge(request: SearchRequest):
    """搜索知识库"""
    results = await retriever.search(request.query, request.top_k)
    return [r.to_dict() for r in results]
```

---

## 🔐 认证机制

### 1. GitHub OAuth

```python
# app/auth/github_oauth.py
async def exchange_code_for_token(code: str):
    """用授权码换取 Token"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code
            },
            headers={"Accept": "application/json"}
        )
        return response.json().get("access_token")
```

### 2. JWT Token

```python
# app/auth/token.py
import jwt

def create_access_token(user_id: str) -> str:
    """创建 JWT Token"""
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

def verify_token(token: str) -> str:
    """验证 Token"""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    return payload.get("sub")
```

---

## 📊 监控和日志

### 1. Loguru 日志

```python
from loguru import logger

# 配置日志
logger.add(
    "logs/app.log",
    rotation="10 MB",
    retention="7 days",
    level="INFO"
)

# 使用
logger.info("服务启动")
logger.error(f"错误: {error}")
```

### 2. 健康检查

```python
@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}
```

---

## 🧪 测试

### 1. API 测试

```bash
# 健康检查
curl http://localhost:8001/health

# 匿名登录
curl -X POST http://localhost:8001/api/auth/anonymous

# 对话测试
curl -X POST http://localhost:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "token": "xxx"}'
```

### 2. Docker 测试

```bash
# 查看容器状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 进入容器
docker-compose exec agent-service bash
```

---

## 📝 总结

### 关键点

1. **FastAPI 异步**：使用 async/await，支持高并发
2. **SQLAlchemy 2.0**：异步 ORM，类型提示
3. **pgvector**：PostgreSQL 向量扩展，一体化
4. **Docker 部署**：容器化，方便部署

### 注意事项

1. **数据库连接池**：合理配置 pool_size
2. **Redis 过期**：设置合理的 TTL
3. **错误处理**：捕获异常，优雅降级
4. **日志记录**：方便排查问题

---

## 📚 参考资源

- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 文档](https://docs.sqlalchemy.org/en/20/)
- [pgvector 文档](https://github.com/pgvector/pgvector)
- [Docker 官方文档](https://docs.docker.com/)

---

**上一篇：[项目架构设计](./01-项目架构设计.md)** ← → **下一篇：[RAG 知识库实现](./03-RAG知识库实现.md)** →
