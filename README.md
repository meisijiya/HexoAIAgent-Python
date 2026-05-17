# 🤖 Hexo 智能体 Agent 插件

> 为 Hexo 博客注入 AI 灵魂 —— 知识库问答 + 联网搜索 + 记忆系统

[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED)](https://docs.docker.com/compose/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## 📖 项目简介

**Hexo AI Agent** 是一个为 Hexo 博客添加 AI 对话能力的插件系统。访客可以在博客右下角打开对话窗口，与 AI 助手"老江湖"聊天：

- 📚 **知识库问答**：基于你的博客文章（pgvector + DashScope embedding）
- 🌐 **联网搜索**：实时搜索补充信息（百度千帆 API）
- 🧠 **记忆系统**：短期记忆 + 语义记忆混合检索
- 🔐 **GitHub OAuth 登录**：区分匿名游客和注册用户
- 📊 **功能分级**：匿名 10次/天，登录 100次/天

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                     Hexo 博客 (GitHub Pages)              │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Chic 主题 /js/agent-widget.js    (?v=sha256)     │   │
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
│  │  ├─ history_manager  → 短期记忆 + 语义记忆         │   │
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

## 🧠 三 Agent 架构详解

### 路由决策链路

```
用户消息 → ChatAgent.phase1_classify()
              │
              │ LLM 轻量分类 (max_tokens=150, temperature=0)
              │ 输出纯 JSON: {"route":"knowledge|search|react|null", ...}
              │
     ┌────────┼────────┬────────┐
     ▼        ▼        ▼        ▼
 knowledge  search   react    null
     │        │        │        │
     │        │        │        └→ ChatAgent.chat_stream() 纯聊天
     │        │        │
     │        │        └→ ReactAgent.run()
     │        │              ├─ 思考链展示
     │        │              ├─ web_search / knowledge_search
     │        │              └─ 最终综合分析
     │        │
     │        └→ SearchAgent.search()
     │               ├─ 百度千帆 API
     │               └─ SEO 摘要 + 来源链接
     │
     └→ KnowledgeAgent.process()
            ├─ 按 categories/tags 过滤
            ├─ retriever.search() pgvector 语义检索
            ├─ LLM 辅助相关性筛选（候选＞3）
            └─ 构建 chunk 级别上下文 → 流式回答
```

### 1. ChatAgent — 对话路由中枢

**位置**：`agent-service/app/agents/chat_agent.py`

**职责**：
- 维护老江湖人设（`PERSONALITY_PROMPT`）
- 管理对话风格（`CHAT_STYLE`）
- Phase1：LLM 轻量分类 → 决定调哪个子 Agent
- Phase2：纯聊天时流式输出（逐字）

**Skill 系统**：Skill 是路由的权威来源，动态生成 Phase1 分类提示词：

```python
SKILLS = {
    "knowledge": {
        "triggers": ["怎么", "如何", "配置", "部署", "教程", "原理", ...],
        "route_json": '{"route":"knowledge", ...}'
    },
    "search": {
        "triggers": ["上网搜", "最新", "新闻", "百度", ...],
        "route_json": '{"route":"search", ...}'
    },
    "react": {
        "triggers": ["对比", "分析", "优缺点", "推荐", "区别", ...],
        "route_json": '{"route":"react", ...}'
    },
}
```

**匿名用户路由**：跳过 Phase1，`force_tool="knowledge"`，直接走知识库 Agent。

**登录用户**：Phase1 LLM 提取 `categories`/`tags` → 透传给 KnowledgeAgent 做精准过滤。

---

### 2. KnowledgeAgent — 知识库 RAG

**位置**：`agent-service/app/agents/knowledge_agent.py`

**流程**：
```
用户消息 + categories + tags
    │
    ▼
retriever.search(query, categories, tags, top_k=5, threshold=0.45)
    │  ← pgvector cosine 语义检索 + JSONB GIN 索引过滤
    │
    ▼
候选 > 3 && (categories or tags)?
    │ YES → LLM 辅助相关性筛选（挑真正相关的 chunk）
    │ NO  → 全部使用
    │
    ▼
_build_context(chunks) → 拼接 chunk 级别上下文（不传整篇）
    │
    ▼
DeepSeek 流式生成回答 + 文章来源链接
```

**关键优化**：
- 分块前剥离 YAML front-matter（避免元数据污染向量）
- 标签统一小写化 + 大小写不敏感搜索
- JSONB GIN 索引（`idx_chunks_metadata_gin`）→ 筛选查询 1.24ms
- 分类/标签无匹配时兜底走文章清单 API → LLM 总结

---

### 3. SearchAgent — 联网搜索

**位置**：`agent-service/app/agents/search_agent.py`

**流程**：
```
用户消息 → 百度千帆 web_search API（top_k=5）
    │
    ▼
SEO 结果格式化 → 来源列表
    │
    ▼
前端 addSearchSources() 展示可点击链接
```

---

### 4. ReActAgent — 工具调用链

**位置**：`agent-service/app/agents/react_agent.py`

**模式**：ReAct（Reasoning + Acting）→ 思考 → 决策 → 行动 → 观察 → 综合

```
用户复杂问题（对比/分析/推荐）
    │
    ▼
思考链展示：列出分析维度
    │
    ▼
需要外部信息？
    │ YES → 调用 tool (web_search / knowledge_search)
    │        │
    │        └→ 获取结果 → 回到思考链
    │ NO  → 直接给出综合分析
    │
    ▼
流式输出最终答案
```

---

## 🧠 记忆系统

### 双层架构

```
┌─────────────────────────────────────────┐
│           短期记忆 (Redis LIST)            │
│  最近 5 轮对话 (user + assistant)         │
│  TTL: 30 天                              │
│  用途：保持当前对话上下文连贯               │
└──────────────┬──────────────────────────┘
               │ 每 5 轮触发一次 batch embed
               ▼
┌─────────────────────────────────────────┐
│          语义记忆 (pgvector)              │
│  仅嵌入用户消息 + embedding 向量           │
│  跨会话检索：cosine top-3                │
│  用途：跨会话关联相关话题                  │
└─────────────────────────────────────────┘
```

### 混合检索流程

```
用户发消息
    │
    ├→ history_manager.get_context(session_id)
    │      ├─ 短期记忆：Redis 最近 5 轮
    │      └─ 语义记忆：pgvector 余弦 top-3（跨会话）
    │
    └→ 拼接 → 注入 LLM system prompt
```

### 前端展示

- 语义记忆命中时显示徽章：`🧠 回忆了 X 个话题`（5 秒自动消失）
- 知识库结果显示文章链接 + 相似度分数

---

## 🛠️ 工具系统

**位置**：`agent-service/app/agents/tools.py`

### 已注册工具

| 工具名 | 类 | 用途 | 状态 |
|--------|-----|------|------|
| `web_search` | `WebSearchTool` | 百度千帆搜索（100次/天免费额度） | ✅ 启用 |
| `knowledge_search` | `KnowledgeSearchTool` | pgvector 语义检索知识库 | ✅ 启用 |

### WebSearchTool

```
输入：查询词 → POST 百度千帆 web_search API
    │
    ├→ 正常：返回 top-5 结果（标题+URL+摘要）
    ├→ 429：额度耗尽 → 友好提示
    └→ 超时：连接异常 → 友好提示
```

配置：`.env` 中设置 `BAIDU_SEARCH_API_KEY`

### KnowledgeSearchTool

```
输入：查询词 → retriever.search(query, top_k=5)
    │
    └→ 返回 chunk 内容 + 相似度分数 + 文章来源
```

被 ReActAgent 调用，用于工具链中的知识库检索步骤。

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
│   ├── .dockerignore
│   └── app/
│       ├── main.py                 # FastAPI 入口 + 生命周期管理
│       ├── config.py               # 全局配置（pydantic-settings）
│       ├── api/                    # REST API 路由
│       │   ├── auth.py             # GitHub OAuth + 匿名登录
│       │   ├── chat.py             # SSE 流式对话
│       │   ├── knowledge.py        # 知识库 CRUD + 分类/标签筛选
│       │   └── search.py           # 联网搜索
│       ├── agents/                 # AI Agent 层
│       │   ├── chat_agent.py       # 对话路由（Phase1 LLM 分类）
│       │   ├── knowledge_agent.py  # RAG 知识库问答
│       │   ├── search_agent.py     # 联网搜索
│       │   ├── react_agent.py      # ReAct 工具调用链
│       │   └── tools.py            # 工具定义（WebSearch / KnowledgeSearch）
│       ├── core/                   # 核心服务
│       │   ├── database.py         # asyncpg + pgvector
│       │   ├── redis.py            # 会话上下文 + 限流
│       │   ├── history_manager.py  # 短期记忆 + 语义记忆
│       │   ├── cleanup.py          # 定时清理（30天过期 + 匿名7天）
│       │   ├── git_sync.py         # Git 轮询博文自动同步
│       │   ├── llm.py              # DeepSeek 客户端
│       │   ├── prompt_builder.py   # 系统提示词构建
│       │   └── retry_handler.py    # LLM 重试逻辑
│       ├── knowledge/              # 知识库模块
│       │   ├── chunker.py          # Markdown 分块
│       │   ├── embedder.py         # DashScope embedding
│       │   ├── retriever.py        # pgvector 检索 + JSONB 过滤
│       │   └── frontmatter_parser.py
│       ├── models/                 # SQLAlchemy 模型
│       │   ├── user.py, session.py, message.py, memory.py, knowledge.py
│       ├── auth/                   # 认证模块
│       │   ├── token.py            # JWT 签发/验证
│       │   └── github_oauth.py     # GitHub OAuth 流程
│       └── static/                 # 前端静态文件（服务器直接提供，Hexo 无需拷贝）
│           ├── agent-widget.js     # 对话 Widget（__API_BASE__ 占位符，sync-widget.sh 注入）
│           ├── agent-widget.css    # Widget 样式
│           └── oauth-callback.html # OAuth 回调页
│
├── hexo-widget/                    # Hexo 插件（NPM 包，本地 hexo server 调试用）
│   ├── package.json
│   ├── index.js                    # 注入 JS/CSS 标签
│   ├── version.json                # 内容哈希（sync-widget.sh 自动生成）
│   ├── layout/widget.swig
│   └── source/
│       ├── js/agent-widget.js      # Widget JS（同 static/ 副本）
│       └── css/agent-widget.css    # Widget CSS（同 static/ 副本）
│
└── scripts/
    ├── agent.sh                    # 🎯 交互式运维脚手架（一键管理所有操作）
    ├── sync-widget.sh              # Widget 构建（注入 API_BASE + 版本哈希）
    ├── sync_articles.py            # 文章增量同步（date + hash key + --reset）
    ├── import_articles.py          # 手动导入博文到知识库
    └── init-db.sql                 # PostgreSQL 初始化（pgvector 扩展）
```

---

## 📜 脚本使用指南

### `scripts/agent.sh` — 交互式运维脚手架

**一键管理所有操作**，自动检测本地/远程模式。

```bash
bash scripts/agent.sh
```

```
╔══════════════════════════════════════════╗
║       🤖 Hexo Agent 运维脚手架           ║
╠══════════════════════════════════════════╣
║  💻 本地模式                             ║
╚══════════════════════════════════════════╝

  🐳 Docker 服务:
    1. 启动服务      4. 查看日志      7. 重建容器
    2. 停止服务      5. 进入容器
    3. 重启服务      6. 健康检查

  📦 知识库同步:
    a. 增量同步文章    c. 预览变更
    b. 全量重置文章    d. 手动导入 (旧脚本)

  🎨 前端:
    f. 同步 Widget 到 Hexo 主题

  🧹 其他:
    x. 手动执行清理    q. 退出
```

**远程模式**：本地无 Docker 时，配置 `agent-service/.env` 中 `SERVER_HOST` → 自动 SSH 代理所有服务器命令。

---

### `scripts/sync-widget.sh` — Widget 构建脚本

将 `.env` 中的 `API_BASE` 注入 Widget JS 占位符，生成版本哈希。**注：博客直接从服务器加载 Widget，不再拷贝到 Hexo 目录。**

```bash
bash scripts/sync-widget.sh
```

**工作流**：
1. 读取 `.env` 中 `API_BASE`（如 `http://localhost:8001` 或 `https://你的域名`）
2. 替换 JS 源码中 `__API_BASE__` 占位符
3. 计算 JS 内容 SHA256 → 写入 `hexo-widget/version.json`
4. Docker 重建后，服务器 `/static/agent-widget.js` 即包含正确 API 地址

---

### `scripts/sync_articles.py` — 文章增量同步

基于 front-matter date + 路径 hash 做增量同步，避免重复导入。

```bash
# 增量同步（只导入新增/变更文章）
python3 scripts/sync_articles.py

# 预览变更（不实际写入）
python3 scripts/sync_articles.py --dry-run

# 全量重置（删除全部 → 重新导入）
python3 scripts/sync_articles.py --reset
```

**同步记录**：`.sync_record.json` 记录每篇文章的 hash、日期、URL。

```json
{
  "2024-03-15_a3f8c2d1": {
    "title": "Hexo 部署教程",
    "hash": "a3f8c2d1e9b0f4a5c6d7e8f9a0b1c2d3",
    "url": "https://xn--ljhfjm-dl0o.top/2024/03/15/hexo-deploy/",
    "synced_at": "2026-05-17T10:30:00+08:00"
  }
}
```

---

### `scripts/import_articles.py` — 手动导入博文

```bash
# 导入指定目录
python3 scripts/import_articles.py /path/to/hexo/source/_posts

# 强制重新导入（覆盖已有）
python3 scripts/import_articles.py /path/to/hexo/source/_posts --force

# 清空知识库
python3 scripts/import_articles.py --clear

# Docker 中使用
docker exec hexo-agent-service python scripts/import_articles.py /data/blog-repo/source/_posts
```

---

### `scripts/init-db.sql` — 数据库初始化

PostgreSQL 容器首次启动时自动执行，包含：
- 表结构（users, sessions, messages, knowledge_articles, knowledge_chunks, memories）
- GIN 索引（`idx_chunks_metadata_gin` 用于 JSONB 过滤）
- pgvector 扩展 + 余弦相似度索引

---

## 🚀 快速部署

### 前置要求

- 云服务器 (Ubuntu 24.04，2C4G 以上)
- 已备案域名或公网 IP
- GitHub 账号（用于 OAuth App 注册）
- [可选] 备用 GitHub 仓库（用于 Git 自动同步博文）

### 第一步：配置环境变量

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
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:4001,https://你的域名,https://meisijiya.github.io,http://<服务器IP>:8001

# ---- 博客配置 ----
BLOG_BASE_URL=https://你的域名
HEXO_THEME_PATH=/path/to/your/hexo/themes/Chic
BLOG_ARTICLES_DIR=/path/to/your/hexo/source/_posts

# ---- AI API Keys ----
DEEPSEEK_API_KEY=sk-xxx
DASHSCOPE_API_KEY=sk-xxx

# ---- 搜索（可选） ----
BAIDU_SEARCH_API_KEY=xxx

# ---- 远程运维（可选） ----
# 本地无 Docker 时，agent.sh 通过 SSH 连接服务器
SERVER_HOST=你的服务器IP
SERVER_USER=root
SERVER_PROJECT_PATH=/opt/hexo-agent
```

### 第二步：启动 Docker 服务

```bash
# 生产启动
docker compose -f docker-compose.prod.yml up -d

# 查看日志
docker compose -f docker-compose.prod.yml logs -f agent-service

# 健康检查
curl http://localhost:8001/health
```

### 第三步：导入博客文章到知识库

```bash
bash scripts/sync-widget.sh                  # 同步前端 Widget
python3 scripts/sync_articles.py --reset     # 全量同步文章到知识库
```

### 第四步：配置 Hexo 主题（Chic 主题为例）

Widget 由服务器直接提供，Hexo 博客**不需要拷贝任何文件**。只需在主题中加配置：

#### 4a. 主题配置文件 `_config.yml` 添加

```yaml
agent_widget:
  enable: true
  api_url: https://你的域名       # 服务器地址（生产）或 http://localhost:8001（本地调试）
  position: bottom-right
```

#### 4b. 创建 Widget 注入模板 `layout/_partial/agent-widget.ejs`

```ejs
<% if (theme.agent_widget && theme.agent_widget.enable !== false) { %>
    <% var apiUrl = theme.agent_widget.api_url || 'http://localhost:8001'; %>
    <!-- Agent Widget -->
    <link rel="stylesheet" href="<%= apiUrl %>/static/agent-widget.css">
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <script src="<%= apiUrl %>/static/agent-widget.js"></script>
<% } %>
```

#### 4c. 布局引入 `layout/layout.ejs`

在 `<head>` 中加入：

```ejs
<%- partial('_partial/agent-widget',{cache: false}) %>
```

#### 4d. 重新构建并部署 Hexo

```bash
hexo clean && hexo generate && hexo deploy
```

> 💡 以上 3 个文件就是你博客需要的全部前端代码。Widget JS/CSS 由服务器 FastAPI `/static/` 提供，更新 Widget 时只需 `docker compose build` 重建服务端，无需重新部署 Hexo。

### 第五步：申请 GitHub OAuth App

1. 登录 GitHub → **Settings** → **Developer settings** → **OAuth Apps**
2. 点 **New OAuth App** 或修改现有 App
3. 填写：
   - **Homepage URL**: `https://你的域名`
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
| `HEXO_THEME_PATH` | ✅ | - | Hexo 主题本地路径（sync-widget.sh 用） |
| `BLOG_ARTICLES_DIR` | - | - | 博文源码目录（sync_articles.py 用） |
| `GIT_SYNC_ENABLED` | - | `false` | 是否启用 Git 自动轮询同步 |
| `GIT_REPO_URL` | - | - | 备用 GitHub 仓库 URL |
| `BAIDU_SEARCH_API_KEY` | - | - | 百度千帆搜索 API Key |
| `REACT_MAX_ITERATIONS` | - | `5` | ReAct Agent 最大迭代次数 |
| `HISTORY_LIMIT` | - | `3` | 对话历史轮数 |
| `SERVER_HOST` | - | - | agent.sh 远程模式服务器地址 |
| `SERVER_USER` | - | `root` | agent.sh 远程模式 SSH 用户 |
| `SERVER_PROJECT_PATH` | - | `/opt/hexo-agent` | 服务器上项目路径 |

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

## 🎯 功能特性

### 用户体系
- **匿名游客**：IP 限流 10次/天，仅知识库
- **GitHub 登录**：user_id 限流 100次/天，全功能
- JWT Token（HS256，7 天有效期）
- 前端配额显示：🟡游客·剩余X次 / 🟢已登录·剩余X次

### 会话管理
- 软删除 + 30 天自动过期
- 匿名用户 7 天自动清理
- 用户可手动清除历史会话
- 每天凌晨 3 点清理定时触发

### 知识库
- 博文分块 → DashScope embedding → pgvector 存储
- 语义检索 top-5 + 阈值 0.45
- 分类/标签 JSONB GIN 索引筛选
- LLM 辅助相关性筛选（候选 >3 时触发）
- 前链接：`BLOG_BASE_URL + /YYYY/MM/DD/ + _posts下相对路径`

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

1. **SECRET_KEY 务必更换**：生产用 `openssl rand -hex 32` 生成强随机密钥
2. **Client Secret 仅显示一次**：申请 OAuth App 后立即保存
3. **防火墙**：只开放 8001 端口，不要暴露 5432/6379 到公网
4. **单 worker 模式**：定时任务（cleanup + git_sync）未加分布式锁，生产多 worker 需注意
5. **Token 无吊销**：JWT 签发后 7 天内有效，暂无黑名单
6. **Docker root 用户**：当前容器以 root 运行，后续建议加 `USER appuser`

---

## 📈 后续规划

- [ ] 知识库管理后台
- [ ] Token 吊销机制（Redis 黑名单）
- [ ] Docker 非 root 用户运行
- [ ] Alembic 数据库迁移
- [ ] 生产监控（Prometheus + Grafana）
- [ ] 多 worker 分布式锁
- [ ] LLM 响应缓存

---

## 📄 许可证

MIT License © 2026 ljh2923
