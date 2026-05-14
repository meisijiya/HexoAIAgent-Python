# Hexo 智能体 Agent 插件 - 开发计划

## 📌 项目概述

为 Hexo + Chic 主题博客网站添加 AI Agent 对话功能，支持知识库检索、Web 搜索、会话记忆等功能。

---

## 🎯 最终技术栈

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| **前端** | Hexo + Chic 主题 + Agent Widget | 小人图标 + 弹窗对话 |
| **后台管理** | Java + 若依框架 | 知识库管理、对话日志、配置管理 |
| **AI 服务** | Python + FastAPI | 对话 Agent、知识库 Agent、搜索 Agent |
| **数据库** | PostgreSQL + pgvector | 向量存储 + 业务数据 |
| **缓存** | Redis | 短期会话记忆 |
| **登录** | GitHub OAuth | 技术博客读者友好 |
| **LLM** | DeepSeek V4 Flash / MiMo v2.5 | 成本优先 |
| **Embedding** | DashScope text-embedding-v4 | 1024 维向量 |
| **服务器** | 腾讯云 4GB + 2GB | 内网互通 |

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        GitHub Pages                                  │
│                     Hexo + Chic 主题                                 │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    Agent Widget                                │  │
│  │   ┌─────────┐        ┌─────────────────┐                      │  │
│  │   │  小人    │ ──▶    │  对话弹窗        │                      │  │
│  │   │ (可拖拽) │        │  - 消息列表      │                      │  │
│  │   └─────────┘        │  - 输入框        │                      │  │
│  │                      │  - 登录按钮      │                      │  │
│  │                      └─────────────────┘                      │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     4GB 服务器（腾讯云）                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  PostgreSQL   │  │    Redis     │  │   若依后台    │              │
│  │  (pgvector)   │  │  (短期记忆)  │  │   (Java)     │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                         Nginx                                 │  │
│  │   /api/*  ──反向代理──▶  Python AI 服务 (2GB 服务器)           │  │
│  │   /admin/* ──▶  若依后台 (本机)                                │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                              内网通信
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     2GB 服务器（腾讯云）                              │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    Python AI 服务 (FastAPI)                    │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │                    Orchestrator                          │  │  │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐   │  │  │
│  │  │  │  对话 Agent  │  │ 知识库 Agent │  │  搜索 Agent   │   │  │  │
│  │  │  └─────────────┘  └─────────────┘  └───────────────┘   │  │  │
│  │  └─────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📦 项目结构

```
hexo-agent/
├── agent-service/                  # Python AI 服务
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI 入口
│   │   ├── config.py               # 配置管理
│   │   │
│   │   ├── agents/                 # Agent 模块
│   │   │   ├── __init__.py
│   │   │   ├── base.py             # Agent 基类
│   │   │   ├── chat_agent.py       # 对话 Agent
│   │   │   ├── knowledge_agent.py  # 知识库 Agent
│   │   │   └── search_agent.py     # 搜索 Agent
│   │   │
│   │   ├── core/                   # 核心模块
│   │   │   ├── __init__.py
│   │   │   ├── orchestrator.py     # 调度器
│   │   │   ├── llm.py              # LLM 封装
│   │   │   └── memory.py           # 会话记忆（Redis）
│   │   │
│   │   ├── knowledge/              # 知识库模块
│   │   │   ├── __init__.py
│   │   │   ├── chunker.py          # 文章分块
│   │   │   ├── embedder.py         # Embedding 服务
│   │   │   └── retriever.py        # 向量检索
│   │   │
│   │   ├── auth/                   # 认证模块
│   │   │   ├── __init__.py
│   │   │   ├── github_oauth.py     # GitHub OAuth
│   │   │   └── token.py            # Token 管理
│   │   │
│   │   ├── api/                    # API 路由
│   │   │   ├── __init__.py
│   │   │   ├── chat.py             # 对话 API
│   │   │   ├── knowledge.py        # 知识库 API
│   │   │   └── auth.py             # 认证 API
│   │   │
│   │   ├── models/                 # 数据模型
│   │   │   ├── __init__.py
│   │   │   ├── user.py             # 用户模型
│   │   │   ├── session.py          # 会话模型
│   │   │   ├── message.py          # 消息模型
│   │   │   └── knowledge.py        # 知识库模型
│   │   │
│   │   └── utils/                  # 工具函数
│   │       ├── __init__.py
│   │       └── helpers.py
│   │
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── hexo-widget/                    # Hexo 前端插件
│   ├── source/
│   │   ├── css/
│   │   │   └── agent-widget.css
│   │   └── js/
│   │       ├── agent-widget.js
│   │       ├── chat-ui.js
│   │       └── auth.js
│   ├── layout/
│   │   └── widget.swig
│   └── package.json
│
├── knowledge-sync/                 # 知识库同步脚本
│   ├── sync.py                     # 同步逻辑
│   ├── scraper.py                  # 博客文章抓取
│   └── config.py
│
└── docs/                           # 文档
    ├── api.md
    ├── deployment.md
    └── development.md
```

---

## 🗄️ 数据库设计

### PostgreSQL 表结构

```sql
-- ==================== 用户相关 ====================

-- 用户表
CREATE TABLE agent_users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    github_id       BIGINT UNIQUE,
    github_username VARCHAR(100),
    nickname        VARCHAR(50),
    email           VARCHAR(100),
    avatar_url      VARCHAR(255),
    is_anonymous    BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW(),
    last_active_at  TIMESTAMP
);

CREATE INDEX idx_users_github ON agent_users(github_id);

-- ==================== 会话相关 ====================

-- 会话表
CREATE TABLE agent_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES agent_users(id) ON DELETE CASCADE,
    title           VARCHAR(200),
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_sessions_user ON agent_sessions(user_id, updated_at DESC);

-- 对话消息表
CREATE TABLE agent_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID REFERENCES agent_sessions(id) ON DELETE CASCADE,
    role            VARCHAR(20) NOT NULL,
    content         TEXT NOT NULL,
    agent_type      VARCHAR(20),
    metadata        JSONB,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_messages_session ON agent_messages(session_id, created_at);

-- ==================== 知识库相关 ====================

-- 知识库文章表
CREATE TABLE knowledge_articles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(200) NOT NULL,
    url             VARCHAR(500) UNIQUE,
    content         TEXT,
    source          VARCHAR(20) DEFAULT 'blog',
    synced_at       TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- 文章分块表（含向量）
CREATE TABLE knowledge_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id      UUID REFERENCES knowledge_articles(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    embedding       VECTOR(1024),
    metadata        JSONB,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_chunks_article ON knowledge_chunks(article_id);
CREATE INDEX idx_chunks_vector ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops);

-- 同步日志表
CREATE TABLE knowledge_sync_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_type    VARCHAR(20),
    status          VARCHAR(20),
    articles_count  INTEGER DEFAULT 0,
    error_message   TEXT,
    created_at      TIMESTAMP DEFAULT NOW(),
    completed_at    TIMESTAMP
);
```

### Redis 数据结构

```
1. 会话上下文（短期记忆）
   Key:    session:{session_id}:context
   Type:   List
   TTL:    24 小时

2. 用户会话列表缓存
   Key:    user:{user_id}:sessions
   Type:   Sorted Set
   TTL:    1 小时

3. OAuth 状态缓存
   Key:    oauth:state:{state}
   Type:   String
   TTL:    10 分钟

4. API 限流
   Key:    rate:{user_id}:{minute}
   Type:   String (counter)
   TTL:    1 分钟
```

---

## 🔄 Git 提交策略

每完成一个功能模块立即提交，便于溯源和回滚。

### 提交规范

```
<type>(<scope>): <description>

类型(type):
- feat: 新功能
- fix: 修复
- docs: 文档
- style: 格式
- refactor: 重构
- test: 测试
- chore: 构建/工具

示例:
feat(auth): 实现 GitHub OAuth 登录
fix(chat): 修复流式输出中断问题
feat(knowledge): 添加文章分块功能
```

### 提交节点

| 序号 | 模块 | 提交信息 | 验证方式 |
|------|------|----------|----------|
| 1 | 项目骨架 | `feat(init): 初始化 FastAPI 项目结构` | 服务能启动 |
| 2 | 数据库连接 | `feat(db): 添加 PostgreSQL 连接和模型` | 能创建表 |
| 3 | Redis 连接 | `feat(redis): 添加 Redis 连接` | 能读写缓存 |
| 4 | OAuth 登录 | `feat(auth): 实现 GitHub OAuth 登录` | 能获取用户信息 |
| 5 | LLM 封装 | `feat(llm): 封装 DeepSeek/MiMo API` | 能调用 API |
| 6 | 对话 Agent | `feat(chat): 实现对话 Agent` | 能对话 |
| 7 | 知识库 Agent | `feat(knowledge): 实现 RAG 知识库` | 能检索 |
| 8 | 搜索 Agent | `feat(search): 实现搜索 Agent` | 能搜索 |
| 9 | 调度器 | `feat(orchestrator): 实现 Agent 调度` | 完整流程 |

---

## 📅 开发阶段

### 阶段一：Python AI 服务核心（Week 1-2）

**目标**: 搭建 AI 服务基础，实现对话功能

#### Week 1: 基础框架 + 对话能力

- [ ] **Day 1-2: 项目搭建**
  - FastAPI 项目结构
  - PostgreSQL 连接（SQLAlchemy + asyncpg）
  - Redis 连接（aioredis）
  - 配置管理（pydantic-settings）
  - 日志配置

- [ ] **Day 3-4: GitHub OAuth 登录**
  - GitHub OAuth 流程实现
  - 用户表 CRUD
  - Token 生成与验证（JWT）
  - 登录/注销 API

- [ ] **Day 5-7: 对话 Agent**
  - LLM 封装（DeepSeek/MiMo API）
  - 对话消息存储
  - Redis 会话管理（短期记忆）
  - 流式输出 API（SSE）

#### Week 2: 知识库能力

- [ ] **Day 8-10: 知识库 Agent**
  - 文章分块逻辑（三阶段：按标题 → 按字符 → 合并小块）
  - DashScope Embedding 服务封装
  - pgvector 向量存储
  - 相似度检索 API

- [ ] **Day 11-12: 搜索 Agent**
  - /搜索 命令解析
  - Web 搜索 API 集成（DuckDuckGo / SerpAPI）
  - 搜索结果格式化

- [ ] **Day 13-14: 调度器 + 联调**
  - Orchestrator 实现
  - Agent 路由逻辑
  - 端到端测试

---

### 阶段二：前端接入（Week 3）

**目标**: 博客上能看到小人，能对话

- [ ] **Day 15-16: 基础 UI**
  - 小人图标（SVG）
  - 拖拽功能实现
  - 位置记忆（localStorage）
  - 响应式适配（PC/移动端）

- [ ] **Day 17-18: 对话弹窗**
  - 弹窗组件
  - 消息列表
  - 输入框
  - 智能定位（找空位弹出）

- [ ] **Day 19-21: 功能联调**
  - GitHub OAuth 登录按钮
  - SSE 流式接收
  - 会话管理（新建/切换）
  - 历史对话展示（最近 10 条会话）

---

### 阶段三：搜索 + 知识库同步（Week 4）

**目标**: 搜索可用，知识库自动更新

- [ ] **Day 22-23: 知识库同步**
  - GitHub Actions webhook
  - 博客文章抓取逻辑
  - 增量更新策略
  - 同步状态记录

- [ ] **Day 24-25: 性能优化**
  - 对话上下文裁剪策略
  - Embedding 缓存
  - API 响应优化
  - 错误处理完善

- [ ] **Day 26-28: 测试与修复**
  - 完整流程测试
  - 边界情况处理
  - Bug 修复

---

### 阶段四：后台管理系统（Week 5-6）

**目标**: 管理后台，可视化管理

#### Week 5: 若依框架学习

- [ ] **若依项目搭建**
- [ ] **基础 CRUD 理解**
- [ ] **权限系统**
- [ ] **菜单配置**

#### Week 6: 业务模块开发

- [ ] **知识库管理模块**
  - 文章列表
  - 手动上传/编辑
  - 分块预览

- [ ] **对话日志模块**
  - 会话列表
  - 对话详情
  - 统计图表

- [ ] **Agent 配置模块**
  - Prompt 模板管理
  - 模型参数配置
  - 知识库同步状态

---

### 阶段五：优化上线（Week 7）

- [ ] **域名 + HTTPS**
  - 购买域名
  - Nginx 配置
  - SSL 证书（Let's Encrypt）

- [ ] **部署优化**
  - Docker 容器化
  - 进程管理（systemd / pm2）
  - 日志收集

- [ ] **监控告警**
  - API 监控
  - 错误告警
  - 资源监控

- [ ] **正式上线**

---

## 🔑 API 设计

### 对话 API

```
POST /api/chat
Headers:
  X-User-ID: uuid
  X-Auth-Token: jwt-token

Request:
{
    "session_id": "uuid-xxx",      // 可选，不传则新建会话
    "message": "你的 Hexo 主题怎么安装？",
    "command": null                // 或 "/搜索"
}

Response (SSE 流式):
data: {"type": "thinking", "content": "正在分析您的问题..."}
data: {"type": "searching", "content": "正在检索知识库..."}
data: {"type": "answer", "content": "关于 Hexo 主题安装，"}
data: {"type": "answer", "content": "您可以按照以下步骤..."}
data: {"type": "done", "sources": ["blog/hexo-install.md"]}
```

### 知识库同步 API

```
POST /api/knowledge/sync
Headers:
  X-Webhook-Secret: github-actions-secret

Request:
{
    "trigger": "github_deploy",
    "articles": [
        {
            "url": "https://yourblog.github.io/posts/hexo-guide/",
            "title": "Hexo 完全指南",
            "content": "..."
        }
    ]
}
```

### 认证 API

```
GET /api/auth/github
Response: { "redirect_url": "https://github.com/login/oauth/authorize?..." }

GET /api/auth/github/callback?code=xxx
Response: { "token": "jwt-xxx", "user": { ... } }

GET /api/auth/me
Response: { "id": "...", "nickname": "...", "avatar_url": "..." }
```

---

## 💰 成本预估

| 项目 | 月成本 | 说明 |
|------|--------|------|
| **服务器** | ~100-200 元 | 腾讯云 4GB + 2GB |
| **域名** | ~10 元/年 | .top 域名 |
| **DeepSeek API** | ~10-30 元 | 按量计费，取决于使用量 |
| **DashScope Embedding** | ~5-10 元 | 按量计费 |
| **总计** | ~120-250 元/月 | |

---

## ⚠️ 注意事项

1. **内存管理**: 4GB 服务器需要合理分配内存给 PostgreSQL、Redis、若依
2. **HTTPS**: GitHub Pages 是 HTTPS，调用 HTTP API 会被浏览器拦截
3. **CORS**: 需要配置跨域允许 GitHub Pages 域名访问
4. **限流**: 需要对 API 进行限流，防止滥用
5. **备份**: 定期备份 PostgreSQL 数据

---

## 🐳 Docker 部署策略

使用 Docker Compose 编排所有服务，方便开发测试和部署。

### 本地开发环境

```yaml
# docker-compose.yml
version: '3.8'

services:
  # PostgreSQL + pgvector
  postgres:
    image: pgvector/pgvector:pg16
    container_name: hexo-agent-postgres
    environment:
      POSTGRES_DB: hexo_agent
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Redis
  redis:
    image: redis:7-alpine
    container_name: hexo-agent-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Python AI 服务
  agent-service:
    build:
      context: ./agent-service
      dockerfile: Dockerfile
    container_name: hexo-agent-service
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:password@postgres:5432/hexo_agent
      - REDIS_URL=redis://redis:6379/0
    env_file:
      - ./agent-service/.env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./agent-service:/app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

volumes:
  postgres_data:
  redis_data:
```

### Agent Service Dockerfile

```dockerfile
# agent-service/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 生产环境（4GB 服务器）

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: hexo-agent-postgres
    environment:
      POSTGRES_DB: hexo_agent
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1G

  redis:
    image: redis:7-alpine
    container_name: hexo-agent-redis
    volumes:
      - redis_data:/data
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 256M

  nginx:
    image: nginx:alpine
    container_name: hexo-agent-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./nginx/ssl:/etc/nginx/ssl
    depends_on:
      - agent-service
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

### 常用命令

```bash
# 启动开发环境
docker-compose up -d

# 查看日志
docker-compose logs -f agent-service

# 停止服务
docker-compose down

# 重建镜像
docker-compose up -d --build

# 进入容器
docker-compose exec agent-service bash

# 数据库迁移
docker-compose exec agent-service alembic upgrade head
```

---

## 📚 参考资料

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [pgvector 文档](https://github.com/pgvector/pgvector)
- [DashScope API](https://help.aliyun.com/zh/dashscope/)
- [若依框架](http://doc.ruoyi.vip/)
- [GitHub OAuth](https://docs.github.com/en/developers/apps/building-oauth-apps)

