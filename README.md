# 🤖 Hexo 智能体 Agent 插件

> 为 Hexo 博客注入 AI 灵魂 —— 知识库问答 + 联网搜索 + 记忆系统

[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED)](https://docs.docker.com/compose/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## 📖 项目简介

**Hexo AI Agent** 是一个为 Hexo 博客添加 AI 对话能力的插件系统。访客可以在博客右下角打开对话窗口，与 AI 助手聊天：

- 📚 **知识库问答**：基于你的博客文章（pgvector + DashScope embedding）
- 🌐 **联网搜索**：实时搜索补充信息（百度千帆 API）
- 🧠 **记忆系统**：语义记忆 + 混合检索（Redis + pgvector）
- 🔐 **GitHub OAuth 登录**：区分匿名游客和注册用户
- 📊 **功能分级**：匿名 10次/天，登录 100次/天

---

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                     Hexo 博客 (GitHub Pages)              │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Chic 主题 /js/agent-widget.js                   │   │
│  │  Chic 主题 /css/agent-widget.css                  │   │
│  └──────────────────┬───────────────────────────────┘   │
└─────────────────────┼───────────────────────────────────┘
                      │ HTTP SSE / REST API
                      ▼
┌─────────────────────────────────────────────────────────┐
│               Agent 服务器 (Docker - 云服务器)             │
│  ┌──────────────────────────────────────────────────┐   │
│  │  FastAPI (8001)                                   │   │
│  │  ├─ /api/chat              → SSE 流式对话         │   │
│  │  ├─ /api/auth              → GitHub OAuth 登录    │   │
│  │  ├─ /api/knowledge         → 知识库 CRUD          │   │
│  │  └─ /api/search            → 联网搜索             │   │
│  ├──────────────────────────────────────────────────┤   │
│  │  Agent 层                                         │   │
│  │  ├─ ChatAgent        → 对话路由（Phase1 分类）     │   │
│  │  ├─ KnowledgeAgent   → RAG 知识库问答             │   │
│  │  ├─ SearchAgent      → 联网搜索                   │   │
│  │  └─ ReActAgent       → 工具调用链                  │   │
│  ├──────────────────────────────────────────────────┤   │
│  │  Core                                              │   │
│  │  ├─ history_manager  → 短期记忆（Redis context）    │   │
│  │  ├─ cleanup          → 定时清理（30天过期）         │   │
│  │  └─ git_sync         → Git 轮询博文自动同步        │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐    │
│  │ Postgres │  │  Redis   │  │  外部 API            │    │
│  │+ pgvector│  │  7-alpine│  │  ├─ DeepSeek         │    │
│  │   :5432  │  │   :6379  │  │  ├─ DashScope (向量)  │    │
│  └──────────┘  └──────────┘  │  └─ 百度千帆 (搜索)   │    │
└──────────────────────────────┴──────────────────────────┘
```

### 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vanilla JS (IIFE), SSE, CSS3 |
| 后端框架 | FastAPI (Python 3.11+) |
| 数据库 | PostgreSQL 16 + pgvector |
| 缓存/限流 | Redis 7 |
| AI 模型 | DeepSeek Chat (对话), DashScope text-embedding-v4 (向量) |
| 部署 | Docker Compose (3 容器) |
| 认证 | GitHub OAuth 2.0 + JWT (HS256) |
| 向量检索 | pgvector cosine similarity |
| 搜索引擎 | 百度千帆 / DuckDuckGo |

---

## 📁 项目结构

```
Hexo-智能体Agent插件/
├── docker-compose.yml              # 开发环境 Docker Compose
├── docker-compose.prod.yml         # 生产环境 Docker Compose
├── README.md
│
├── agent-service/                  # 后端 AI 服务
│   ├── Dockerfile                  # Python 多阶段构建镜像
│   ├── .env                        # 环境变量（gitignored）
│   ├── .env.example
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── app/
│       ├── main.py                 # FastAPI 入口 + 生命周期管理
│       ├── config.py               # 全局配置（pydantic-settings）
│       ├── api/                    # REST API 路由
│       │   ├── auth.py             # GitHub OAuth + 匿名登录
│       │   ├── chat.py             # SSE 流式对话
│       │   ├── knowledge.py        # 知识库 CRUD
│       │   └── search.py           # 联网搜索
│       ├── agents/                 # AI Agent 层
│       │   ├── chat_agent.py       # 对话路由（Phase1 LLM 分类）
│       │   ├── knowledge_agent.py  # RAG 知识库问答
│       │   ├── react_agent.py      # ReAct 工具调用链
│       │   └── search_agent.py     # 联网搜索
│       ├── core/                   # 核心服务
│       │   ├── database.py         # asyncpg + pgvector
│       │   ├── redis.py            # 会话上下文 + 限流
│       │   ├── history_manager.py  # 短期记忆 + 语义记忆
│       │   ├── cleanup.py          # 定时清理（30天过期）
│       │   ├── git_sync.py         # Git 轮询博文自动同步
│       │   └── llm.py              # DeepSeek 客户端
│       ├── knowledge/              # 知识库模块
│       │   ├── chunker.py          # Markdown 分块
│       │   ├── embedder.py         # DashScope embedding
│       │   ├── retriever.py        # pgvector 检索
│       │   └── frontmatter_parser.py
│       ├── models/                 # SQLAlchemy 模型
│       │   ├── user.py, session.py, message.py, memory.py, knowledge.py
│       ├── auth/                   # 认证模块
│       │   ├── token.py            # JWT 签发/验证
│       │   └── github_oauth.py     # GitHub OAuth 流程
│       └── static/                 # 前端静态文件
│           ├── agent-widget.js     # 对话 Widget（900+ 行）
│           ├── agent-widget.css    # Widget 样式
│           └── oauth-callback.html # OAuth 回调页
│
├── hexo-widget/                    # Hexo 插件（NPM 包）
│   ├── package.json
│   ├── index.js                    # Hexo 插件入口
│   ├── layout/widget.swig          # Swig 模板注入
│   └── source/
│       ├── js/agent-widget.js      # Widget JS（部署到主题）
│       └── css/agent-widget.css    # Widget CSS（部署到主题）
│
└── scripts/
    ├── setup-server.sh             # 服务器一键初始化脚本
    └── import_articles.py          # 手动导入博文脚本
```

---

## 🚀 快速部署

### 前置要求

- 云服务器 (Ubuntu 24.04，2C4G 以上)
- 已备案域名或公网 IP
- GitHub 账号（用于 OAuth App 注册）
- [可选] 备用 GitHub 仓库（用于 Git 自动同步博文）

### 第一步：服务器初始化

```bash
# SSH 登录服务器
ssh root@<你的服务器IP>

# 运行初始化脚本
curl -fsSL <脚本URL> | bash
# 或手动安装 Docker（参考 scripts/setup-server.sh）
```

### 第二步：配置环境变量

```bash
# 编辑 agent-service/.env
vim agent-service/.env
```

必填配置：

```bash
# ---- 生产环境强制修改 ----
DEBUG=false
SECRET_KEY=<随机生成64位字符串>  # openssl rand -hex 32
POSTGRES_PASSWORD=<强密码>

# ---- GitHub OAuth ----
GITHUB_CLIENT_ID=<你的ClientID>
GITHUB_CLIENT_SECRET=<你的ClientSecret>
GITHUB_REDIRECT_URI=http://<服务器IP>:8001/static/oauth-callback.html

# ---- CORS 白名单 ----
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:4001,https://xn--ljhfjm-dl0o.top,https://meisijiya.github.io,http://<服务器IP>:8001

# ---- 博客配置 ----
BLOG_BASE_URL=https://xn--ljhfjm-dl0o.top

# ---- AI API Keys ----
DEEPSEEK_API_KEY=sk-xxx
DASHSCOPE_API_KEY=sk-xxx

# ---- Git 同步（可选，默认关闭） ----
GIT_SYNC_ENABLED=false
# GIT_REPO_URL=https://github.com/meisijiya/your-backup-repo.git
```

### 第三步：启动 Docker 服务

```bash
# 生产启动
docker compose -f docker-compose.prod.yml up -d

# 查看日志
docker compose -f docker-compose.prod.yml logs -f agent-service

# 健康检查
curl http://localhost:8001/health
```

### 第四步：导入博客文章到知识库

```bash
# 在服务器上执行（需要先把博文目录上传或用 git clone）
docker exec hexo-agent-service python scripts/import_articles.py /data/blog-repo/source/_posts
```

### 第五步：配置 Hexo 主题（Chic 主题示例）

本项目前端 Widget 代码嵌入在 Hexo 主题文件夹中。以 Chic 主题为例：

#### 5a. 复制文件到主题目录

```bash
# 将 Widget 文件复制到 Chic 主题
cp hexo-widget/source/js/agent-widget.js  themes/Chic/source/js/
cp hexo-widget/source/css/agent-widget.css  themes/Chic/source/css/
```

#### 5b. 修改 `agent-widget.js` 中的 API 地址

打开 `themes/Chic/source/js/agent-widget.js`，修改第 8 行：

```javascript
API_BASE: 'http://<你的服务器IP>:8001',   // 生产环境改为实际服务器地址
```

#### 5c. 注入到页面

在主题布局文件中注入 JS/CSS。以 Chic 主题的 `layout/_partial/head.ejs` 和 `layout/_partial/footer.ejs` 为例：

**`layout/_partial/head.ejs` 中 `</head>` 前添加：**

```html
<link rel="stylesheet" href="/css/agent-widget.css">
```

**`layout/_partial/footer.ejs` 中 `</body>` 前添加：**

```html
<script src="/js/agent-widget.js"></script>
```

#### 5d. 重新构建并部署 Hexo

```bash
hexo clean && hexo generate && hexo deploy
```

### 第六步：申请 GitHub OAuth App

1. 登录 GitHub → **Settings** → **Developer settings** → **OAuth Apps**
2. 点 **New OAuth App** 或修改现有 App
3. 填写：
   - **Homepage URL**: `https://xn--ljhfjm-dl0o.top`
   - **Authorization callback URL**: `http://<服务器IP>:8001/static/oauth-callback.html`
4. 拿到 Client ID 和 Client Secret 后更新 `.env`

---

## 🔧 配置参考

### 全部环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `SECRET_KEY` | ✅ | - | JWT 签名密钥（`openssl rand -hex 32`） |
| `DATABASE_URL` | - | pgvector:5432 | PostgreSQL 连接串 |
| `REDIS_URL` | - | redis:6379 | Redis 连接串 |
| `DEBUG` | - | `false` | 调试模式 |
| `GITHUB_CLIENT_ID` | ✅ | - | GitHub OAuth App Client ID |
| `GITHUB_CLIENT_SECRET` | ✅ | - | GitHub OAuth App Client Secret |
| `GITHUB_REDIRECT_URI` | ✅ | - | OAuth 回调 URL |
| `DEEPSEEK_API_KEY` | ✅ | - | DeepSeek API Key |
| `DASHSCOPE_API_KEY` | ✅ | - | DashScope Embedding API Key |
| `ALLOWED_ORIGINS` | ✅ | - | CORS 白名单（逗号分隔） |
| `BLOG_BASE_URL` | ✅ | - | 博客域名（生成文章链接） |
| `GIT_SYNC_ENABLED` | - | `false` | 是否启用 Git 自动轮询同步 |
| `GIT_REPO_URL` | - | - | 备用 GitHub 仓库 URL |
| `GIT_POSTS_PATH` | - | `source/_posts/` | 仓库中博文路径 |
| `GIT_POLL_INTERVAL_MINUTES` | - | `30` | Git 同步间隔（分钟） |

---

## 📝 手动导入博文

```bash
# 本地开发
cd agent-service
python ../scripts/import_articles.py /path/to/hexo/source/_posts

# 强制重新导入所有文章
python ../scripts/import_articles.py /path/to/hexo/source/_posts --force

# 清空知识库
python ../scripts/import_articles.py --clear

# Docker 中使用
docker exec hexo-agent-service python scripts/import_articles.py /data/blog-repo/source/_posts
```

---

## 🎯 功能特性

### 知识库问答 (RAG)
- 博文分块 → DashScope embedding → pgvector 存储
- 语义检索 top-3 + 阈值 0.45
- 结合 DeepSeek 生成回答，带可点击链接

### 对话记忆
- **短期记忆**：Redis LIST 保存最近 5 轮对话
- **语义记忆**：每 5 轮触发 batch embedding（仅嵌入用户消息）
- **混合检索**：Redis 近期 + pgvector 语义 top-3
- 前端徽章："🧠 回忆了 X 个话题"（5 秒消失）

### 用户体系
- **匿名游客**：IP 限流 10次/天，仅知识库
- **GitHub 登录**：user_id 限流 100次/天，全功能
- JWT Token（HS256，7 天有效期）
- 前端配额显示：🟡游客·剩余X次 / 🟢已登录·剩余X次

### 会话管理
- 软删除 + 30 天自动过期
- 每天凌晨 3 点清理
- 用户可手动清除历史会话

---

## 📦 部署文件对比

| 文件 | 用途 | 热重载 | 源码挂载 | DEBUG |
|------|------|--------|----------|-------|
| `docker-compose.yml` | 本地开发 | ✅ | ✅ | true |
| `docker-compose.prod.yml` | 生产部署 | ❌ | ❌ | false |

```bash
# 开发
docker compose up -d

# 生产
docker compose -f docker-compose.prod.yml up -d
```

---

## 🛠️ 常用运维命令

```bash
# 查看日志
docker compose -f docker-compose.prod.yml logs -f agent-service

# 重启服务
docker compose -f docker-compose.prod.yml restart agent-service

# 重建镜像
docker compose -f docker-compose.prod.yml up -d --build agent-service

# 进入容器调试
docker exec -it hexo-agent-service bash

# 手动运行清理
docker exec hexo-agent-service python -c "
import asyncio
from app.core.cleanup import run_cleanup
asyncio.run(run_cleanup())
"

# 重置某 IP 配额
docker exec hexo-agent-redis redis-cli DEL "daily_rate:ip:1.2.3.4:2026-05-17"
```

---

## ⚠️ 注意事项

1. **SECRET_KEY 务必更换**：当前 `.env` 中的是测试用，生产用 `openssl rand -hex 32` 生成
2. **Client Secret 仅显示一次**：申请 OAuth App 后立即保存
3. **防火墙**：只开放 8001 端口，不要暴露 5432/6379 到公网
4. **单 worker 模式**：定时任务（cleanup + git_sync）未加分布式锁，生产多 worker 需注意
5. **Token 无吊销**：JWT 签发后 7 天内有效，暂无黑名单
6. **ALEMBIC 待加**：数据库迁移目前靠手动执行或 `create_all`

---

## 📈 后续规划

- [ ] 知识库管理后台
- [ ] Token 吊销机制（Redis 黑名单）
- [ ] 登录限流（rate:auth:{ip}）
- [ ] Alembic 数据库迁移
- [ ] 生产监控（Prometheus + Grafana）
- [ ] 多 worker 分布式锁

---

## 📄 许可证

MIT License © 2026 ljh2923
