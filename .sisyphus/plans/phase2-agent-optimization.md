# Phase 2: Agent 智能路由优化 + 云端部署

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化意图识别路由，修复知识库问答准确性，完善容错处理，最终部署到云端服务器。

**Architecture:** 采用"知识库优先"策略 — 技术问题默认走知识库 Agent（RAG），仅在知识库无匹配时自动 fallback 到 LLM 自身知识，提示用户是否需要上网搜索。ReAct Agent 作为万能后备，使用 DuckDuckGo API 进行网络搜索。

---

## Context

### 已完成（Phase 1）
- ✅ FastAPI 项目 + Docker Compose（PostgreSQL+pgvector, Redis）
- ✅ 4 个 Agent：Chat / Knowledge / Search / ReAct
- ✅ RAG 系统：Embedding + pgvector 检索 + 动态阈值
- ✅ 54 篇博客文章已导入（含 categories/tags）
- ✅ Hexo Widget：拖拽图标、SSE 流式、Markdown 渲染、暗色模式
- ✅ GitHub OAuth + JWT + 匿名登录
- ✅ 9 篇学习博客 record/
- ✅ DuckDuckGo 搜索集成（SearchAgent）

### 当前问题（本次修复）
1. **意图识别优先级冲突**：搜索关键词（"今天"/"最新"）在知识库之前，导致技术问题被误路由到搜索
2. **ReAct Agent 不调用工具**：LLM 直接编造答案，没有使用 search_knowledge 工具
3. **知识库无匹配时需要手动选择**：当前需要用户点选项，应改为自动 fallback + 提示搜索
4. **参考链接未验证**：可点击链接功能已实现但未测试
5. **ReAct Agent 工具不合理**：search_knowledge 与 KnowledgeAgent 重复，效果更差

### 讨论确认的方案
1. ✅ **知识库优先路由**：技术问题默认走 Knowledge Agent
2. ✅ **搜索触发词扩充**：精准覆盖"上网搜"/"帮我搜"/"百度一下"等
3. ✅ **自动 fallback**：知识库无匹配 → LLM 回答 → 提示是否搜索
4. ✅ **ReAct Agent 作为万能后备**：只在知识库无匹配 + 用户选择搜索时使用
5. ✅ **移除 ReAct 的知识库工具**：避免与 KnowledgeAgent 重复
6. ✅ **添加 web_search 工具**：使用 DuckDuckGo API（免费，无需 API Key）
7. ✅ **对话历史**：默认携带最近 3 轮（可配置）
8. ✅ **配置统一**：历史条数、最大迭代次数统一用环境变量配置
9. ✅ **搜索引擎**：DuckDuckGo API（免费，支持中文）

---

## 文件结构

```
agent-service/app/
├── core/
│   ├── orchestrator.py          # [修改] 意图识别 v3 — 知识库优先 + 搜索触发词扩充
│   ├── config.py                # [修改] 添加 HISTORY_LIMIT、REACT_MAX_ITERATIONS 配置
│   └── history_manager.py       # [修改] 添加 get_recent_history(limit) 方法
├── agents/
│   ├── knowledge_agent.py       # [修改] 容错自动 fallback + 提示搜索选项
│   ├── react_agent.py           # [修改] 强化工具调用 prompt + 使用 web_search 工具
│   ├── tools.py                 # [重构] 移除知识库工具，添加 web_search 工具
│   ├── error_handler.py         # [删除] 不再需要（逻辑合并到 knowledge_agent）
│   └── search_agent.py          # [保留] 作为独立搜索 Agent（/搜索 命令）
├── static/
│   ├── agent-widget.js          # [验证] 参考链接可点击性
│   └── agent-widget.css         # [小调] 参考来源样式
scripts/
└── import_articles.py           # [优化] 添加实际博客 URL
agent-service/
├── .env                         # [修改] 添加配置项
└── Dockerfile                   # [优化] 生产镜像优化
docker-compose.yml               # [添加] SearXNG（可选，暂时不需要）
```

---

## Execution Strategy

```
Wave 1 (并行 — 核心修复，互不依赖):
├── Task 1: Orchestrator 意图识别 v3 — 知识库优先 + 搜索触发词扩充 [quick]
├── Task 2: Knowledge Agent 容错自动 fallback + 提示搜索 [quick]
├── Task 3: tools.py 重构 — 移除知识库工具，添加 web_search [quick]
├── Task 4: ReAct Agent Prompt 强化 + 使用 web_search [quick]
├── Task 5: config.py + history_manager.py 配置统一 [quick]
└── Task 6: error_handler.py 删除（逻辑合并） [quick]

Wave 2 (并行 — 验证 + 优化，依赖 Wave 1):
├── Task 7: 参考链接端到端验证 [unspecified-high]
├── Task 8: import_articles.py 添加实际 URL [quick]
└── Task 9: Widget 参考来源样式优化 [quick]

Wave 3 (串行 — 集成测试):
└── Task 10: Docker 重建 + 全流程集成测试 [unspecified-high]

Wave 4 (并行 — 部署准备):
├── Task 11: 生产环境配置 [quick]
├── Task 12: Docker 生产镜像优化 [quick]
└── Task 13: 部署文档编写 [writing]

Wave FINAL:
└── Task F1: 全量回归测试 [unspecified-high]
```

---

## TODOs

- [ ] 1. Orchestrator 意图识别 v3 — 知识库优先 + 搜索触发词扩充

  **What to do**:
  - 修改 `orchestrator.py` 的 `_quick_classify()` 方法
  - 调整关键词优先级：知识库 > 搜索 > ReAct > 聊天
  - 扩充搜索触发词（精准覆盖，避免误伤）：
    ```python
    search_trigger_patterns = [
        # 明确搜索动作
        "上网搜", "搜一下", "搜搜", "帮我搜", "网上搜",
        "查一下", "查查", "帮我查", "网上查",
        "百度一下", "谷歌一下", "Google一下", "搜狗一下",
        # 明确要求外部信息
        "有没有最新", "最新消息", "最新版本", "最新资讯",
        "最近新闻", "今天新闻", "今日热点",
        # 命令式
        "/搜索", "/search", "/s", "/web",
    ]
    ```
  - 添加优先级规则：先检查知识库关键词，但如果同时有搜索意图，则走搜索
  - ReAct 仅在"对比"/"比较"/"分析"/"推荐"且问题较长（>20字）时触发
  - 默认 fallback 到知识库 Agent（不再 fallback 到 LLM 兜底分类）

  **Must NOT do**:
  - 不要删除 LLM 兜底分类（`_llm_classify`），保留为最终安全网
  - 不要修改 Agent 的接口签名

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **References**:
  - `agent-service/app/core/orchestrator.py:136-200` — 当前 `_quick_classify()` 实现
  - `agent-service/app/core/orchestrator.py:200-226` — 当前 `_llm_classify()` 实现

  **Acceptance Criteria**:
  - [ ] "怎么配置 Hexo" → KNOWLEDGE（不是 SEARCH）
  - [ ] "今天怎么部署 Docker" → KNOWLEDGE（"怎么"优先）
  - [ ] "上网搜一下 Docker 教程" → SEARCH（搜索触发词优先）
  - [ ] "帮我查最新的 Node.js 版本" → SEARCH（"帮我查"+"最新"组合）
  - [ ] "百度一下 Hexo 主题" → SEARCH（"百度一下"优先）
  - [ ] "对比 Redis 和 MySQL" → REACT（多步推理）
  - [ ] "你好" → CHAT
  - [ ] `/搜索 Docker` → SEARCH（斜杠命令）

  **QA Scenarios**:
  ```
  Scenario: 技术问题走知识库
    Tool: Bash (curl)
    Preconditions: Agent 服务运行在 localhost:8001
    Steps:
      1. curl -X POST http://localhost:8001/api/chat -H "Content-Type: application/json" -d '{"message": "怎么配置 Hexo 主题", "session_id": "test-001"}'
      2. 检查响应中 routing.agent_type == "knowledge"
    Expected Result: agent_type 为 "knowledge"
    Evidence: .sisyphus/evidence/task-1-tech-goes-knowledge.txt

  Scenario: 搜索触发词走搜索
    Tool: Bash (curl)
    Preconditions: Agent 服务运行在 localhost:8001
    Steps:
      1. curl -X POST http://localhost:8001/api/chat -H "Content-Type: application/json" -d '{"message": "上网搜一下 Docker 教程", "session_id": "test-002"}'
      2. 检查响应中 routing.agent_type == "search"
    Expected Result: agent_type 为 "search"
    Evidence: .sisyphus/evidence/task-1-search-trigger.txt
  ```

  **Commit**: YES
  - Message: `fix(orchestrator): 知识库优先路由策略 v3 + 搜索触发词扩充`
  - Files: `agent-service/app/core/orchestrator.py`

---

- [ ] 2. Knowledge Agent 容错自动 fallback + 提示搜索

  **What to do**:
  - 修改 `knowledge_agent.py` 的 `search_and_answer_with_info()` 方法
  - 当知识库无匹配时，自动 fallback 到 LLM 自身知识回答
  - 在回答开头添加提示："📚 知识库中未找到相关内容，以下是 AI 参考答案："
  - 在回答结尾显示选项：
    ```python
    yield {
        "type": "options",
        "options": [
            {"label": "上网搜索", "value": "search", "icon": "🔍"},
            {"label": "够了，谢谢", "value": "done", "icon": "✅"}
        ]
    }
    ```
  - 用户选择"上网搜索"后，发送 `trigger_search` 信号

  **Must NOT do**:
  - 不要修改知识库检索逻辑（动态阈值/Top-K）
  - 不要删除 error_handler（保留备用）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **References**:
  - `agent-service/app/agents/knowledge_agent.py:69-75` — 当前无匹配处理
  - `agent-service/app/agents/error_handler.py:148-181` — `_generate_fallback_answer()` 实现

  **Acceptance Criteria**:
  - [ ] 知识库无匹配时自动返回 LLM 回答（不需要用户点选项）
  - [ ] 回答包含"知识库中未找到相关内容"提示
  - [ ] 回答后显示"上网搜索"/"够了"选项
  - [ ] 用户选择"上网搜索"后发送 `trigger_search` 信号

  **QA Scenarios**:
  ```
  Scenario: 知识库无匹配自动 fallback + 提示搜索
    Tool: Bash (curl)
    Preconditions: Agent 服务运行在 localhost:8001
    Steps:
      1. curl -X POST http://localhost:8001/api/chat -H "Content-Type: application/json" -d '{"message": "量子计算是什么", "session_id": "test-003"}' 2>&1
      2. 检查响应包含"知识库中未找到"或"AI"关键词
      3. 检查响应包含 options 类型消息（上网搜索/够了）
    Expected Result: 自动返回 LLM 回答 + 显示搜索选项
    Evidence: .sisyphus/evidence/task-2-auto-fallback.txt
  ```

  **Commit**: YES
  - Message: `fix(knowledge): 知识库无匹配自动 fallback + 提示搜索选项`
  - Files: `agent-service/app/agents/knowledge_agent.py`

---

- [ ] 3. tools.py 重构 — 移除知识库工具，添加 web_search

  **What to do**:
  - 移除 `SearchKnowledgeTool`、`GetArticleTool`、`ListArticlesTool`
  - 添加 `WebSearchTool`（使用 DuckDuckGo API）：
    ```python
    class WebSearchTool(Tool):
        """网络搜索工具（DuckDuckGo）"""
        
        def __init__(self):
            super().__init__(
                name="web_search",
                description="搜索互联网，获取最新信息、教程、新闻等",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词，例如：Docker 部署教程、Hexo 主题推荐"
                        }
                    },
                    "required": ["query"]
                }
            )
        
        async def execute(self, query: str = "", **kwargs) -> str:
            """
            执行网络搜索（DuckDuckGo API）
            
            Args:
                query: 搜索关键词
            
            Returns:
                格式化的搜索结果（标题 + 摘要 + 链接）
            """
            if not query:
                return "错误：缺少搜索关键词"
            
            try:
                from duckduckgo_search import DDGS
                
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=5))
                
                if not results:
                    return f"没有找到关于 '{query}' 的搜索结果"
                
                # 格式化结果
                formatted = []
                for i, r in enumerate(results, 1):
                    formatted.append(
                        f"[{i}] {r['title']}\n"
                        f"链接: {r['href']}\n"
                        f"摘要: {r['body']}"
                    )
                
                return "\n\n".join(formatted)
            
            except Exception as e:
                logger.error(f"网络搜索失败: {e}")
                return f"网络搜索失败：{str(e)}"
    ```
  - 更新 `ToolCollection`，只注册 `web_search` 工具

  **Must NOT do**:
  - 不要修改 `ToolCollection` 的接口

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **References**:
  - `agent-service/app/agents/tools.py` — 当前工具定义
  - `agent-service/app/agents/search_agent.py` — DuckDuckGo 搜索实现（参考）

  **Acceptance Criteria**:
  - [ ] 移除 `search_knowledge`、`get_article`、`list_articles` 工具
  - [ ] 添加 `web_search` 工具（DuckDuckGo API）
  - [ ] 工具返回格式：标题 + 链接 + 摘要

  **QA Scenarios**:
  ```
  Scenario: web_search 工具可用
    Tool: Bash (python)
    Preconditions: Python 环境，网络可用
    Steps:
      1. python -c "from app.agents.tools import tool_collection; import asyncio; result = asyncio.run(tool_collection.call('web_search', {'query': 'Docker 教程'})); print(result[:200])"
      2. 检查返回包含"链接"和"摘要"关键词
    Expected Result: 返回格式化的搜索结果
    Evidence: .sisyphus/evidence/task-3-web-search.txt
  ```

  **Commit**: YES
  - Message: `refactor(tools): 移除知识库工具，添加 web_search（DuckDuckGo）`
  - Files: `agent-service/app/agents/tools.py`

---

- [ ] 4. ReAct Agent Prompt 强化 + 使用 web_search

  **What to do**:
  - 修改 `react_agent.py` 的 `REACT_PROMPT`
  - 添加强制规则：
    - "对于需要搜索信息的问题，你必须使用 web_search 工具"
    - "不要猜测或编造信息，只使用工具返回的真实数据"
    - "参考链接显示搜索结果的原始链接"
  - 添加示例：展示正确的 Thought → Action → Action Input → Observation 流程
  - 使用配置的历史条数（`config.HISTORY_LIMIT`）
  - 使用配置的最大迭代次数（`config.REACT_MAX_ITERATIONS`）

  **Must NOT do**:
  - 不要修改 ReAct 循环逻辑（`process()` 方法）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **References**:
  - `agent-service/app/agents/react_agent.py:24-49` — 当前 REACT_PROMPT
  - `agent-service/app/agents/tools.py` — 新的工具定义（web_search）

  **Acceptance Criteria**:
  - [ ] ReAct Agent 调用 web_search 工具
  - [ ] 不再编造不存在的文章名称
  - [ ] 返回结果包含参考链接

  **QA Scenarios**:
  ```
  Scenario: ReAct 调用 web_search 工具
    Tool: Bash (curl)
    Preconditions: Agent 服务运行在 localhost:8001
    Steps:
      1. curl -X POST http://localhost:8001/api/chat -H "Content-Type: application/json" -d '{"message": "对比 Hexo 和 Hugo 博客框架", "session_id": "test-004"}' 2>&1
      2. 检查响应包含 "Thought" 和 "Action" 关键词（说明走了 ReAct 流程）
      3. 检查响应包含真实链接（不是编造的）
    Expected Result: ReAct 流程执行，调用了 web_search 工具
    Evidence: .sisyphus/evidence/task-4-react-calls-web-search.txt
  ```

  **Commit**: YES
  - Message: `fix(react): 强化工具调用 prompt + 使用 web_search`
  - Files: `agent-service/app/agents/react_agent.py`

---

- [ ] 5. config.py + history_manager.py 配置统一

  **What to do**:
  - 修改 `config.py`，添加配置项：
    ```python
    # 对话历史配置
    HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "3"))
    
    # ReAct 配置
    REACT_MAX_ITERATIONS = int(os.getenv("REACT_MAX_ITERATIONS", "5"))
    
    # 搜索配置
    SEARCH_ENGINE = os.getenv("SEARCH_ENGINE", "duckduckgo")
    ```
  - 修改 `history_manager.py`，添加 `get_recent_history(limit)` 方法：
    ```python
    async def get_recent_history(self, session_id: str, limit: int = None) -> List[Dict]:
        """
        获取最近 N 轮对话历史
        
        Args:
            session_id: 会话 ID
            limit: 获取的轮数（默认使用配置的 HISTORY_LIMIT）
        
        Returns:
            最近 N 轮对话列表
        """
        if limit is None:
            limit = config.HISTORY_LIMIT
        
        history_key = f"history:{session_id}"
        messages = await redis.lrange(history_key, 0, limit * 2 - 1)  # 每轮 2 条（user + assistant）
        return [json.loads(msg) for msg in messages]
    ```
  - 修改 `.env`，添加配置项：
    ```
    # 对话历史配置
    HISTORY_LIMIT=3
    
    # ReAct 配置
    REACT_MAX_ITERATIONS=5
    
    # 搜索配置
    SEARCH_ENGINE=duckduckgo
    ```

  **Must NOT do**:
  - 不要修改现有的 `get_history()` 方法

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **References**:
  - `agent-service/app/config.py` — 当前配置
  - `agent-service/app/core/history_manager.py` — 当前历史管理
  - `agent-service/.env` — 当前环境变量

  **Acceptance Criteria**:
  - [ ] `config.HISTORY_LIMIT` 可配置（默认 3）
  - [ ] `config.REACT_MAX_ITERATIONS` 可配置（默认 5）
  - [ ] `history_manager.get_recent_history(limit)` 方法可用
  - [ ] `.env` 包含新配置项

  **Commit**: YES
  - Message: `config: 统一配置历史条数和 ReAct 迭代次数`
  - Files: `agent-service/app/config.py`, `agent-service/app/core/history_manager.py`, `agent-service/.env`

---

- [ ] 6. error_handler.py 删除（逻辑合并）

  **What to do**:
  - 将 `error_handler.py` 中的 `_generate_fallback_answer()` 逻辑合并到 `knowledge_agent.py`
  - 删除 `error_handler.py` 文件
  - 更新 `knowledge_agent.py` 的 import

  **Must NOT do**:
  - 不要删除 `_suggest_rephrasing()` 方法（保留备用）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **References**:
  - `agent-service/app/agents/error_handler.py` — 当前错误处理
  - `agent-service/app/agents/knowledge_agent.py` — 需要合并逻辑

  **Acceptance Criteria**:
  - [ ] `error_handler.py` 删除
  - [ ] `knowledge_agent.py` 包含 fallback 逻辑
  - [ ] 没有 import 错误

  **Commit**: YES
  - Message: `refactor: 删除 error_handler，逻辑合并到 knowledge_agent`
  - Files: `agent-service/app/agents/knowledge_agent.py`, `agent-service/app/agents/error_handler.py`

---

- [ ] 7. 参考链接端到端验证

  **What to do**:
  - 启动 Docker 服务 + Hexo 本地服务器
  - 在 Widget 中提问知识库中的问题（如"怎么安装 Hexo"）
  - 验证参考来源中的链接是否可点击
  - 验证点击后跳转到正确的博客文章页面
  - 如果链接不正确，检查 `_generate_blog_url()` 方法的 URL 生成逻辑

  **Must NOT do**:
  - 不要修改博客文章的 permalink 格式

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`webapp-testing`]

  **References**:
  - `agent-service/app/agents/knowledge_agent.py` — `_generate_blog_url()` 方法
  - `hexo-widget/source/js/agent-widget.js` — `addSources()` 函数

  **Acceptance Criteria**:
  - [ ] 参考来源显示为可点击链接
  - [ ] 点击链接跳转到正确的博客文章页面

  **Commit**: NO（验证任务）

---

- [ ] 8. import_articles.py 添加实际 URL

  **What to do**:
  - 修改 `scripts/import_articles.py`
  - 根据文章的 date 和 title 生成实际的博客 URL
  - 将 URL 存入文章的 metadata 中
  - 重新导入所有文章

  **Must NOT do**:
  - 不要修改文章的 chunk 逻辑

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **References**:
  - `scripts/import_articles.py` — 当前导入脚本

  **Acceptance Criteria**:
  - [ ] 导入后的文章 metadata 包含实际 URL

  **Commit**: YES
  - Message: `feat(import): 文章导入添加实际博客 URL`
  - Files: `scripts/import_articles.py`

---

- [ ] 9. Widget 参考来源样式优化

  **What to do**:
  - 确保链接颜色与主题一致（亮色/暗色模式）
  - 添加 hover 效果（下划线、颜色变化）

  **Must NOT do**:
  - 不要修改 Widget 的整体布局

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **References**:
  - `agent-service/app/static/agent-widget.css` — 当前样式

  **Acceptance Criteria**:
  - [ ] 参考链接在亮色/暗色模式下可见
  - [ ] hover 时有下划线效果

  **Commit**: YES
  - Message: `style(widget): 参考来源链接样式优化`
  - Files: `agent-service/app/static/agent-widget.css`

---

- [ ] 10. Docker 重建 + 全流程集成测试

  **What to do**:
  - 重建 Docker 镜像：`docker-compose down && docker-compose up -d --build`
  - 运行全流程测试：
    1. 技术问答 → 知识库 Agent → 有参考链接
    2. 知识库无匹配 → 自动 fallback → LLM 回答 + 提示搜索
    3. 用户选择"上网搜索" → ReAct Agent → web_search 工具 → 结果 + 链接
    4. 搜索请求（/搜索） → Search Agent → DuckDuckGo 结果
    5. 对比分析 → ReAct Agent → 调用工具 → 真实数据
    6. 闲聊 → 对话 Agent → 简单回答
  - 记录每个测试的结果

  **Must NOT do**:
  - 不要在测试过程中修改代码

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **References**:
  - `docker-compose.yml` — Docker 编排配置

  **Acceptance Criteria**:
  - [ ] 所有 6 种场景测试通过
  - [ ] 无报错日志

  **Commit**: NO（测试任务）

---

- [ ] 11. 生产环境配置

  **What to do**:
  - 创建 `.env.production` 文件
  - 配置生产环境变量：
    - `DEBUG=false`
    - `CORS_ORIGINS=https://meisijiya.github.io`
    - `DATABASE_URL=postgresql+asyncpg://...`
    - `REDIS_URL=redis://...`
    - `HISTORY_LIMIT=3`
    - `REACT_MAX_ITERATIONS=5`
  - 修改 `docker-compose.yml` 添加 production profile

  **Must NOT do**:
  - 不要提交 `.env.production` 到 git

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **References**:
  - `agent-service/.env` — 当前开发环境配置

  **Acceptance Criteria**:
  - [ ] `.env.production` 文件创建
  - [ ] `docker-compose.yml` 支持 production profile

  **Commit**: YES
  - Message: `config: 生产环境配置`
  - Files: `docker-compose.yml`, `.gitignore`

---

- [ ] 12. Docker 生产镜像优化

  **What to do**:
  - 优化 `agent-service/Dockerfile`：
    - 使用 multi-stage build 减小镜像体积
    - 添加 healthcheck
    - 设置非 root 用户
  - 添加 `.dockerignore` 文件

  **Must NOT do**:
  - 不要修改应用代码

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **References**:
  - `agent-service/Dockerfile` — 当前 Dockerfile

  **Acceptance Criteria**:
  - [ ] 镜像体积减小 20%+
  - [ ] healthcheck 正常工作

  **Commit**: YES
  - Message: `perf(docker): 生产镜像优化`
  - Files: `agent-service/Dockerfile`, `.dockerignore`

---

- [ ] 13. 部署文档编写

  **What to do**:
  - 创建 `docs/deployment.md`
  - 包含内容：
    - 云服务器要求（2GB+ RAM）
    - Docker 安装步骤
    - 环境变量配置
    - 域名 + HTTPS 配置（Nginx + Let's Encrypt）
    - 数据库备份策略
    - 常见问题排查

  **Must NOT do**:
  - 不要包含敏感信息

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: []

  **References**:
  - `docker-compose.yml` — Docker 编排配置

  **Acceptance Criteria**:
  - [ ] 文档包含完整的部署步骤
  - [ ] 文档包含常见问题排查

  **Commit**: YES
  - Message: `docs: 部署文档`
  - Files: `docs/deployment.md`

---

## Final Verification Wave

- [ ] F1. **全流程回归测试**
  - 技术问答 → 知识库 Agent → 有参考链接 → 链接可点击
  - 知识库无匹配 → 自动 fallback → LLM 回答 + 提示搜索
  - 用户选择"上网搜索" → ReAct Agent → web_search → 结果 + 链接
  - 搜索请求（/搜索） → Search Agent → DuckDuckGo 结果
  - 对比分析 → ReAct Agent → 调用工具 → 真实数据
  - 闲聊 → 对话 Agent → 简单回答

---

## Commit Strategy

| Task | Commit Message | Files |
|------|---------------|-------|
| 1 | `fix(orchestrator): 知识库优先路由策略 v3 + 搜索触发词扩充` | orchestrator.py |
| 2 | `fix(knowledge): 知识库无匹配自动 fallback + 提示搜索选项` | knowledge_agent.py |
| 3 | `refactor(tools): 移除知识库工具，添加 web_search（DuckDuckGo）` | tools.py |
| 4 | `fix(react): 强化工具调用 prompt + 使用 web_search` | react_agent.py |
| 5 | `config: 统一配置历史条数和 ReAct 迭代次数` | config.py, history_manager.py, .env |
| 6 | `refactor: 删除 error_handler，逻辑合并到 knowledge_agent` | knowledge_agent.py, error_handler.py |
| 8 | `feat(import): 文章导入添加实际博客 URL` | import_articles.py |
| 9 | `style(widget): 参考来源链接样式优化` | agent-widget.css |
| 11 | `config: 生产环境配置` | docker-compose.yml, .gitignore |
| 12 | `perf(docker): 生产镜像优化` | Dockerfile, .dockerignore |
| 13 | `docs: 部署文档` | deployment.md |

---

## Success Criteria

### 验证命令
```bash
# 1. 技术问答走知识库
curl -X POST http://localhost:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "怎么配置 Hexo 主题", "session_id": "test"}'
# 期望: agent_type = "knowledge", 包含参考链接

# 2. 知识库无匹配自动 fallback
curl -X POST http://localhost:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "量子计算是什么", "session_id": "test"}'
# 期望: 自动返回 LLM 回答 + 显示搜索选项

# 3. ReAct 调用 web_search
curl -X POST http://localhost:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "对比 Hexo 和 Hugo", "session_id": "test"}'
# 期望: 包含 Thought/Action，调用 web_search，返回真实链接

# 4. 搜索触发词
curl -X POST http://localhost:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "上网搜一下 Docker 教程", "session_id": "test"}'
# 期望: agent_type = "search"
```

### 最终检查清单
- [ ] 技术问题 → 知识库 Agent（不是搜索）
- [ ] 搜索触发词 → 搜索 Agent（精准匹配）
- [ ] 知识库无匹配 → 自动 LLM 回答 + 提示搜索选项
- [ ] 用户选择"上网搜索" → ReAct Agent → web_search → 结果 + 链接
- [ ] ReAct Agent → 调用工具（不编造）
- [ ] 参考链接 → 可点击跳转
- [ ] Docker 生产镜像 → 优化完成
- [ ] 部署文档 → 完整可用
