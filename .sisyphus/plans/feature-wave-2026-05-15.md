# Feature Wave：OAuth登录 + 记忆优化 + 路由重构 + 人格设计

## TL;DR

> **Quick Summary**: 四合一功能开发：GitHub OAuth 弹窗登录、多轮记忆滑动窗口+语义检索、Agent路由按信息源分流、对话Agent注入"老江湖"人格。TDD模式从零搭建测试。

> **Deliverables**:
> - GitHub OAuth 弹窗登录（匿名保留），用户头像/昵称展示
> - 对话记忆：近期N轮注入 + 旧历史向量语义召回
> - 路由重构：合并双系统，查→知识库，上网→搜索，对比→ReAct
> - Chat Agent 系统提示词：老江湖人格 v3（黑瘦高、爱房间门、口头禅 eggegg）

> **Estimated Effort**: Large
> **Parallel Execution**: YES - 5 waves
> **Critical Path**: 测试基建 → OAuth 回调页 → 记忆基建 → 前端集成 → 最终验证

---

## Context

### Original Request
用户提出四个开发需求：
1. GitHub OAuth 登录
2. 多轮上下文记忆优化（支持条数、容错处理）
3. 知识库 Agent 触发关键字优化（"查"/"搜索"→知识库，"上网"→搜索）
4. 对话 Agent 系统提示词重设计（老江湖人格）

### Interview Summary

**GitHub OAuth**：
- 后端 `github_oauth.py` + `auth.py` 已完整实现 OAuth 流程
- 缺失：前端登录按钮、OAuth 回调 HTML 页面（postMessage 回传 token）
- 选择弹窗模式（window.open），匿名登录保留

**多轮记忆**：
- 当前 Redis 存 20 条但只读 10 条，单条截断 200 字，字符估算非 token
- 选择滑动窗口 + 语义检索方案
- 近期 N 轮直接注入，旧历史做 embedding + pgvector 向量召回

**路由优化**：
- 当前 Orchestrator 和 ChatAgent 有两套 `_quick_classify`，存在冲突
- Metis 发现：Orchestrator 的 SEARCH_TRIGGERS 包含 `"查一下"`，在知识库检查之前就被拦截
- 选择按信息源分流方案，合并两套路由逻辑

**Chat 人格**：
- 当前 system prompt 仅一句话："你是一个友好的智能助手"
- 设计「老江湖」人格 v3：皮肤黝黑、瘦高 178cm、爱伴侣"房间门"、口头禅"eggegg"、喜欢发呆、爱秀恩爱

**Research Findings**：
- 项目已配置 pgvector + DashScope embedding（仅用于知识库）
- 项目零测试基础设施（无 pytest、无 conftest、无 tests/ 目录）
- OAuth redirect_uri 当前指向 API JSON 端点，popup 模式需改为 HTML 页面
- 需要确认 GitHub OAuth App 是否已注册、CLIENT_ID/SECRET 是否配置

### Metis Review

**Identified Gaps** (addressed)：
- 🔥 OAuth redirect_uri 架构冲突 → 新建 `oauth-callback.html` 作为 GitHub App redirect_uri，HTML 调 API 后 postMessage
- 🔥 路由双系统冲突严重度被低估 → 合并 orchestrator + chat_agent 关键词列表，统一 `_quick_classify`
- 📉 记忆系统比描述更基础 → 需要新建对话历史向量表、embedding 管线
- 🧪 零测试基础设施 → Wave 0 先搭测试框架
- JWT 无 refresh token → 暂不处理（用户未提），过期后提示重新登录

---

## Work Objectives

### Core Objective
在现有 Hexo Agent 插件基础上，完成四个功能的开发：GitHub OAuth 登录集成、对话记忆语义检索升级、Agent 路由关键词重构、Chat Agent 人格注入。

### Concrete Deliverables
- `agent-service/app/static/oauth-callback.html` — OAuth 回调页面
- `agent-service/app/static/agent-widget.js` — 前端 OAuth + 用户信息展示
- `agent-service/app/static/agent-widget.css` — 登录区样式
- `agent-service/app/core/history_manager.py` — 记忆模块重构
- `agent-service/app/models/memory.py` — 对话历史向量表
- `agent-service/app/core/orchestrator.py` — 路由合并重构
- `agent-service/app/agents/chat_agent.py` — 老江湖人格 prompt 注入
- `tests/` 目录 — 测试基础设施 + 核心用例

### Definition of Done
- [ ] `pytest tests/` → 全部通过
- [ ] GitHub 弹窗登录 → 拿到 token → 显示头像用户名
- [ ] 多轮对话 → 旧历史可被语义召回
- [ ] "查 Hexo 配置" → 路由到知识库 Agent
- [ ] "上网搜最新新闻" → 路由到搜索 Agent
- [ ] 对话 Agent 每条回复体现老江湖人格

### Must Have
- GitHub OAuth 弹窗登录（匿名入口保留）
- 记忆滑动窗口 + 语义检索（近期 5 轮 + 旧历史向量 top-K 召回）
- 路由按信息源精准分流（查→知识库，上网→搜索，对比→ReAct）
- 老江湖人格 system prompt 注入

### Must NOT Have (Guardrails)
- 不删除后端现有 OAuth 端点（`/api/auth/github` 和 `/api/auth/github/callback` 保持不变）
- 不修改 GitHub OAuth App redirect_uri 配置（oauth-callback.html 做中转，API 端点不变）
- 不删除 ChatAgent 内部 `_quick_classify`（作为兜底，Orchestrator 优先）
- 不修改 ReAct Agent 的流式输出逻辑
- 不修改知识库 Agent 的检索逻辑
- 老江湖人格不包含色情、暴力、政治敏感内容

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: NO (需从零搭建)
- **Automated tests**: TDD
- **Framework**: pytest + pytest-asyncio + httpx (AsyncClient for FastAPI)
- **TDD**: 每个 task 先写 RED（失败测试）→ GREEN（最小实现）→ REFACTOR

### Test Infrastructure Setup (Wave 0)
- 安装 pytest, pytest-asyncio, pytest-cov, httpx
- 创建 `tests/conftest.py`（test client fixture, test DB, test Redis mock）
- 创建 `tests/` 目录结构

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Frontend/UI**: Playwright (webapp-testing skill) - 打开浏览器、点击按钮、断言 DOM、截图
- **API/Backend**: Bash (curl) - 发请求、断言状态码 + 响应字段
- **Python Module**: Bash (pytest) - 运行测试、验证输出

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 0 (测试基建 — 阻塞所有后续):
├── Task 0: 安装测试依赖 + conftest.py [quick]
└── Task 1: .env.example + 测试配置 [quick]

Wave 1 (基础层 — MAX PARALLEL):
├── Task 2: OAuth 回调 HTML 页面 [quick]
├── Task 3: 对话记忆向量表 + 迁移 [quick]
├── Task 4: 路由关键词合并重构 [quick]
├── Task 5: 老江湖人格 prompt 注入 [quick]
└── Task 6: 记忆模块 HistoryManager 重构 [deep]

Wave 2 (TDD 核心 — MAX PARALLEL):
├── Task 7: OAuth 前端按钮 + UI 状态 [visual-engineering]
├── Task 8: 记忆语义检索管线 [deep]
├── Task 9: 路由集成测试 + 边界用例 [unspecified-high]
└── Task 10: 老江湖人格对话集成测试 [unspecified-high]

Wave 3 (集成 + 前端完善):
├── Task 11: OAuth 端到端流程联调 [deep]
├── Task 12: 记忆模块端到端验证 [deep]
├── Task 13: 全路由回归测试 [unspecified-high]
└── Task 14: Docker 重建 + 博客同步 [quick]

Wave FINAL (验证):
├── Task F1: Plan Compliance Audit (oracle)
├── Task F2: Code Quality Review (unspecified-high)
├── Task F3: Real Manual QA (unspecified-high)
└── Task F4: Scope Fidelity Check (deep)
```

### Critical Path
Task 0 → Task 2 → Task 7 → Task 11 → F1-F4
Task 0 → Task 6 → Task 8 → Task 12 → F1-F4
Task 0 → Task 4 → Task 9 → Task 13 → F1-F4

### Agent Dispatch Summary
- **Wave 0**: 2 tasks → `quick`
- **Wave 1**: 5 tasks → 4 `quick` + 1 `deep`
- **Wave 2**: 4 tasks → 1 `visual-engineering`, 1 `deep`, 2 `unspecified-high`
- **Wave 3**: 4 tasks → 2 `deep`, 1 `unspecified-high`, 1 `quick`
- **FINAL**: 4 tasks → `oracle`, `unspecified-high`, `unspecified-high`, `deep`

---

## TODOs

- [x] 0. 安装测试依赖 + 创建 conftest.py

  **What to do**:
  - 创建 `agent-service/requirements-dev.txt`，加入 `pytest`, `pytest-asyncio`, `pytest-cov`, `httpx`, `pytest-mock`
  - 创建 `tests/` 目录结构：`tests/conftest.py`, `tests/test_auth/`, `tests/test_memory/`, `tests/test_routing/`, `tests/test_chat/`
  - 在 `conftest.py` 中：
    - `@pytest.fixture` 创建 `AsyncClient(app)` test client
    - `@pytest.fixture` 创建测试数据库 session（使用 SQLite 内存库或 mock）
    - `@pytest.fixture` mock Redis 连接
    - `@pytest.fixture` 创建测试用户 + token
  - 在 `conftest.py` 中 mock `get_db` dependency override
  - 写一个 smoke test：`test_health()` → `GET /health` → 200

  **Must NOT do**:
  - 不修改生产数据库配置
  - 不引入重型测试框架（只用 pytest 生态）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 纯配置文件 + 简单 fixture，无复杂逻辑
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `test-driven-development`: 手动执行 TDD 步骤，暂不需要

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 0 (with Task 1)
  - **Blocks**: All subsequent tasks need test infra
  - **Blocked By**: None

  **References**:
  - `agent-service/app/main.py` - FastAPI app 入口，需要了解 app 对象创建方式
  - `agent-service/app/core/database.py` - `get_db` dependency，需要 mock
  - `agent-service/app/core/redis.py` - Redis 连接函数，需要 mock
  - `agent-service/app/config.py` - Settings，测试时需覆盖 DATABASE_URL

  **Acceptance Criteria**:
  - [ ] `pytest tests/ -v` → PASS（smoke test 通过）
  - [ ] `tests/conftest.py` 包含所有 fixture
  - [ ] `requirements-dev.txt` 包含所有测试依赖

  **QA Scenarios**:
  ```
  Scenario: Smoke test health endpoint
    Tool: Bash (curl)
    Preconditions: pytest 已安装，conftest.py 已创建
    Steps:
      1. cd agent-service && python -m pytest tests/test_health.py -v
      2. 检查输出包含 "PASSED"
    Expected Result: 至少 1 个测试通过，0 失败
    Failure Indicators: ImportError, fixture 未找到, 测试失败
    Evidence: .sisyphus/evidence/task-0-smoke-test.txt

  Scenario: Fixture 可用性验证
    Tool: Bash (pytest)
    Preconditions: conftest.py 完整
    Steps:
      1. python -m pytest --collect-only tests/
      2. 检查收集到的测试列表
    Expected Result: 所有测试用例被正确收集，无收集错误
    Failure Indicators: "ERROR collecting", fixture not found
    Evidence: .sisyphus/evidence/task-0-fixture-collect.txt
  ```

  **Commit**: YES (groups with Task 1)
  - Message: `chore(test): setup pytest test infrastructure`
  - Files: `tests/conftest.py`, `requirements-dev.txt`, `tests/test_health.py`

- [x] 1. 创建 .env.example + 测试环境配置

  **What to do**:
  - 创建 `agent-service/.env.example` 文件，列出所有环境变量（含注释），敏感值用占位符
  - 在 `conftest.py` 中设置测试环境变量（override SECRET_KEY, DATABASE_URL 等）
  - 确保 GitHub OAuth 相关变量有清晰的注释说明如何获取

  **Must NOT do**:
  - 不包含真实密钥/密码
  - 不覆盖生产 .env

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 纯文档 + 配置
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 0 (with Task 0)
  - **Blocks**: None directly
  - **Blocked By**: None

  **References**:
  - `agent-service/app/config.py` - Settings 类定义，列出所有变量
  - `agent-service/app/auth/github_oauth.py:17-19` - GitHub OAuth 端点 URL
  - `agent-service/.env` (if exists) - 当前配置

  **Acceptance Criteria**:
  - [ ] `.env.example` 包含所有 `config.py` 中定义的变量
  - [ ] 敏感值使用占位符（`your-xxx-here`）
  - [ ] GitHub OAuth 配置有获取说明

  **QA Scenarios**:
  ```
  Scenario: .env.example 完整性检查
    Tool: Bash (grep)
    Preconditions: .env.example 已创建
    Steps:
      1. 对比 config.py 中 Settings 类字段和 .env.example 变量
      2. grep -c "=" .env.example → 应 >= config.py 字段数
    Expected Result: .env.example 覆盖所有配置项
    Failure Indicators: 缺少关键变量（GITHUB_CLIENT_ID, DEEPSEEK_API_KEY 等）
    Evidence: .sisyphus/evidence/task-1-env-check.txt
  ```

  **Commit**: YES (groups with Task 0)
  - Message: `chore: add .env.example and test config`
  - Files: `.env.example`

---

- [x] 2. 创建 OAuth 回调 HTML 页面（oauth-callback.html）

  **What to do**:
  - 创建 `agent-service/app/static/oauth-callback.html`
  - 页面逻辑：
    1. 从 URL query string 提取 `code` 和 `state`
    2. 调用 `GET /api/auth/github/callback?code=xxx&state=xxx`
    3. 解析返回的 JSON → 提取 `token` 和 `user` 信息
    4. `window.opener.postMessage({type: "github-oauth-success", token, user}, "*")`
    5. 显示 "登录成功，窗口即将关闭... eggegg～"
    6. 2 秒后 `window.close()`
  - 错误处理：API 失败时显示错误信息，postMessage 发送失败事件
  - 样式：简洁居中，匹配 Chic 主题配色

  **Must NOT do**:
  - 不修改 `/api/auth/github/callback` 端点逻辑
  - 不在 HTML 中硬编码敏感信息
  - 不修改 GitHub OAuth App 的 redirect_uri（用当前 callback API 端点不变）

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: 前端 HTML 页面，涉及 UI 样式和 postMessage 通信
  - **Skills**: [`frontend-design`]
    - `frontend-design`: 设计简洁美观的回调页面

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 3, 4, 5, 6)
  - **Blocks**: Task 7 (OAuth 前端按钮)
  - **Blocked By**: Task 0 (测试基建)

  **References**:
  - `agent-service/app/api/auth.py:43-98` - `/api/auth/github/callback` 端点的返回格式
  - `agent-service/app/static/agent-widget.css` - 现有配色变量 (--agent-primary 等)
  - `agent-service/app/auth/github_oauth.py:22-41` - 授权 URL 构建方式

  **Acceptance Criteria**:
  - [ ] TDD: `tests/test_auth/test_oauth_callback.py` → RED（先写测试，模拟 postMessage）
  - [ ] `oauth-callback.html` 可正常从 GitHub 回调加载
  - [ ] 成功时 postMessage 包含 `{token, user}`
  - [ ] 失败时 postMessage 包含 `{error}` 且页面显示错误信息
  - [ ] 2 秒后自动关闭窗口

  **QA Scenarios**:
  ```
  Scenario: OAuth 回调成功流程
    Tool: Playwright (webapp-testing)
    Preconditions: 后端运行中，Mock OAuth callback 返回成功
    Steps:
      1. 打开 oauth-callback.html?code=test_code&state=test_state
      2. 等待页面加载完成
      3. 检查页面显示 "登录成功"
      4. 断言 window.opener.postMessage 被调用，参数包含 token 字段
      5. 等待 3 秒后检查窗口是否关闭
    Expected Result: postMessage 发送成功，窗口自动关闭
    Failure Indicators: postMessage 未调用、页面报错、窗口未关闭
    Evidence: .sisyphus/evidence/task-2-oauth-success.png

  Scenario: OAuth 回调失败处理
    Tool: Playwright
    Preconditions: 后端返回 400 错误
    Steps:
      1. 打开 oauth-callback.html?code=invalid&state=invalid
      2. 等待页面加载
      3. 检查页面显示错误信息（非空白页）
      4. 断言 postMessage 发送了 error 事件
    Expected Result: 错误友好展示，不白屏
    Failure Indicators: 白屏、无错误提示、postMessage 未发送
    Evidence: .sisyphus/evidence/task-2-oauth-error.png
  ```

  **Commit**: YES
  - Message: `feat(oauth): add OAuth callback HTML page with postMessage`
  - Files: `agent-service/app/static/oauth-callback.html`, `tests/test_auth/test_oauth_callback.py`

- [x] 3. 创建对话记忆向量表 + 数据库迁移

  **What to do**:
  - 创建 `agent-service/app/models/memory.py`，定义 `ConversationMemory` 模型
  - embedding 列类型 pgvector(1024)，建 IVFFlat 索引
  - 确保 Docker 中 pgvector 可正常创建表

  **Must NOT do**: 不修改现有 sessions/messages 表

  **Recommended Agent Profile**:
  - **Category**: `quick` — 单个 SQLAlchemy 模型
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 1 (with Tasks 2,4,5,6)
  - **Blocks**: Task 8 | **Blocked By**: Task 0

  **References**:
  - `agent-service/app/models/user.py` — 模型风格
  - `agent-service/app/knowledge/retriever.py` — pgvector 检索参考
  - `agent-service/app/config.py:48-50` — embedding 配置

  **Acceptance Criteria**:
  - [ ] TDD: `tests/test_memory/test_memory_model.py` → RED
  - [ ] Docker 中验证 `conversation_memories` 表存在，embedding 列为 vector(1024)

  **QA Scenarios**:
  ```
  Scenario: 向量表创建验证
    Tool: Bash (docker exec)
    Steps: docker exec hexo-agent-postgres psql -U postgres -d hexo_agent -c "\d conversation_memories"
    Expected Result: embedding 列类型为 vector
    Evidence: .sisyphus/evidence/task-3-vector-table.txt
  ```

  **Commit**: YES — `feat(memory): add ConversationMemory model with pgvector embedding`
  - Files: `agent-service/app/models/memory.py`

- [x] 4. 路由关键词合并重构

  **What to do**:
  - Orchestrator SEARCH_TRIGGERS 仅保留明确外部搜索词 → 移除 `"查一下"`, `"帮我查"`
  - 知识库关键词新增 `"查"`, `"搜索"`, `"检索"`, `"找一下"`
  - chat_agent.py 同步更新两套关键词列表
  - 检查顺序：搜索触发词 → ReAct → 知识库 → 对话

  **Must NOT do**: 不删除 ChatAgent 内部 `_quick_classify`

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 1 parallel | **Blocks**: Task 9 | **Blocked By**: Task 0

  **References**:
  - `agent-service/app/core/orchestrator.py:31-63,122-165`
  - `agent-service/app/agents/chat_agent.py:24-48,173-225`

  **Acceptance Criteria**:
  - [ ] TDD: `tests/test_routing/test_keywords.py` → RED
  - [ ] "查一下 Docker" → knowledge | "上网搜最新" → search | "对比 React Vue" → react | "你好" → chat

  **QA Scenarios**:
  ```
  Scenario: 路由回归
    Tool: Bash (pytest) → pytest tests/test_routing/test_keywords.py -v
    Expected Result: 7+ 测试 PASS
    Evidence: .sisyphus/evidence/task-4-routing-test.txt
  ```

  **Commit**: YES — `fix(routing): reorganize trigger keywords`
  - Files: `orchestrator.py`, `chat_agent.py`, `tests/test_routing/test_keywords.py`

- [x] 5. 老江湖人格 System Prompt 注入

  **What to do**:
  - `chat_agent.py` 新增 `LAOJIANGHU_SYSTEM_PROMPT` 常量
  - `_direct_answer()` 方法 system message 替换为老江湖 prompt
  - 确保多轮对话中人格不丢失

  **Must NOT do**: 不改 ReAct/知识库/搜索 Agent prompt

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 1 parallel | **Blocks**: Task 10 | **Blocked By**: Task 0

  **References**: `chat_agent.py:428-438`

  **Acceptance Criteria**:
  - [ ] TDD: `tests/test_chat/test_personality.py` → RED
  - [ ] 回复包含 "老江湖" + "eggegg"，技术问题正常回答

  **QA Scenarios**:
  ```
  Scenario: 人格验证 → curl POST /api/chat "你好"
    Expected Result: 回复含 "老江湖" 或 "eggegg"
    Evidence: .sisyphus/evidence/task-5-personality-hello.txt
  ```

  **Commit**: YES — `feat(chat): inject Laojianhu personality system prompt`
  - Files: `chat_agent.py`, `tests/test_chat/test_personality.py`

- [x] 6. 记忆模块 HistoryManager 重构

  **What to do**:
  - `get_history()` 新增 `mode` 参数：`"recent"` / `"semantic"` / `"hybrid"`
  - `hybrid` 模式：近期 5 轮直接返回 + 旧历史 embedding 语义检索 top-K
  - 新增 `_get_semantic_context(session_id, query)` → embedding + pgvector 检索
  - 新增 `save_memory_embedding(session_id, role, content)` → 双写 Redis + pgvector
  - 使用 tiktoken 精确计算 token

  **Must NOT do**: 不删除 Redis 存储，保持向后兼容

  **Recommended Agent Profile**: `deep` — embedding + 向量检索 + 双写
  **Parallelization**: Wave 1 parallel | **Blocks**: Tasks 8, 12 | **Blocked By**: Tasks 0, 3

  **References**:
  - `history_manager.py` — 重构目标
  - `redis.py:81-126` — 现有上下文接口
  - `knowledge/retriever.py` — embedding + pgvector 参考

  **Acceptance Criteria**:
  - [ ] TDD: `tests/test_memory/test_history_manager.py` → RED
  - [ ] hybrid 模式返回近期 + 语义旧历史
  - [ ] tiktoken 精确计算 token
  - [ ] Redis 不受影响

  **QA Scenarios**:
  ```
  Scenario: 混合召回 → pytest test_history_manager.py
    Expected Result: 近期 5 轮 + 语义 top-3
    Evidence: .sisyphus/evidence/task-6-hybrid-recall.txt
  ```

  **Commit**: YES — `feat(memory): refactor HistoryManager with sliding window + semantic retrieval`
  - Files: `history_manager.py`, `tests/test_memory/test_history_manager.py`

- [x] 7. OAuth 前端集成：登录按钮 + 用户信息展示

  **What to do**:
  - `agent-widget.js` 修改登录区域：
    - 新增 `handleGithubLogin()` 完整实现：
      1. `fetch GET /api/auth/github` → 获取 `authorize_url`
      2. `window.open(authorize_url, "github-oauth", "width=600,height=700")`
      3. 监听 `message` 事件 → 收到 `{type: "github-oauth-success", token, user}` → 保存 token、更新 UI
      4. 收到 `{type: "github-oauth-error"}` → 显示错误提示
    - 更新 `updateUI()` 方法：登录后显示头像 (`user.avatar_url`) + 昵称 (`user.nickname`)
    - 保留匿名登录按钮，添加 GitHub 登录按钮（并排或上下）
  - `agent-widget.css` 新增样式：
    - `.hexo-agent-login-buttons` 两列布局
    - `.hexo-agent-github-btn` GitHub 黑色按钮样式
    - `.hexo-agent-user-info` 用户信息栏（头像 + 昵称 + 退出）
  - 新增 `window.addEventListener("message", ...)` 全局监听 OAuth 回调消息

  **Must NOT do**:
  - 不移除匿名登录功能
  - 不修改 OAuth callback HTML 页面

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: 前端 UI + 事件监听 + CSS 样式
  - **Skills**: [`webapp-testing`]
    - `webapp-testing`: 用 Playwright 测试登录流程

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 2 (with Tasks 8,9,10)
  - **Blocks**: Task 11 | **Blocked By**: Task 2 (OAuth 回调页)

  **References**:
  - `agent-service/app/static/agent-widget.js:352-375` — 现有登录/UI 逻辑
  - `agent-service/app/static/agent-widget.js:363-365` — `handleGithubLogin()` 占位函数
  - `agent-service/app/api/auth.py:23-40` — `/api/auth/github` 返回格式
  - `agent-service/app/static/oauth-callback.html` — Task 2 创建的回调页
  - `agent-service/app/static/agent-widget.css:67-84` — 现有 trigger 按钮样式

  **Acceptance Criteria**:
  - [ ] TDD: `tests/test_auth/test_oauth_frontend.py` → RED（Playwright 测试）
  - [ ] 点击 GitHub 按钮 → 弹出授权窗口
  - [ ] OAuth 回调成功 → token 保存到 localStorage
  - [ ] 登录后显示用户头像 + 昵称
  - [ ] 匿名登录按钮仍然可用
  - [ ] 退出登录 → 清除 token + 恢复匿名状态

  **QA Scenarios**:
  ```
  Scenario: GitHub 登录按钮点击
    Tool: Playwright
    Preconditions: 代理 widget 页面已加载
    Steps:
      1. page.click('.hexo-agent-github-btn')
      2. 检查 window.open 被调用（mock）
      3. 检查 URL 包含 github.com/login/oauth/authorize
    Expected Result: 弹窗打开 GitHub 授权页
    Failure Indicators: 按钮无响应、URL 错误
    Evidence: .sisyphus/evidence/task-7-github-btn-click.png

  Scenario: OAuth 回调 postMessage 接收
    Tool: Playwright
    Steps:
      1. page.evaluate 模拟 postMessage({type:"github-oauth-success", token:"test_jwt", user:{nickname:"老江湖",avatar_url:"..."}})
      2. 检查 widget 顶部显示 "老江湖" 头像和昵称
      3. 检查 localStorage 中 token 已保存
    Expected Result: UI 更新为已登录状态
    Failure Indicators: UI 不变、token 未保存
    Evidence: .sisyphus/evidence/task-7-login-success.png

  Scenario: 匿名登录仍然可用
    Tool: Playwright
    Steps:
      1. page.click('.hexo-agent-anonymous-btn')
      2. 检查正常登录流程
    Expected Result: 匿名登录不受影响
    Evidence: .sisyphus/evidence/task-7-anonymous-works.png
  ```

  **Commit**: YES
  - Message: `feat(oauth): add GitHub login button and user profile display`
  - Files: `agent-widget.js`, `agent-widget.css`, `tests/test_auth/test_oauth_frontend.py`

- [x] 8. 记忆语义检索管线实现

  **What to do**:
  - 在 `history_manager.py` 中实现 `_get_semantic_context()`：
    1. 调用 DashScope API 生成 query embedding
    2. 使用 pgvector 余弦相似度检索 `conversation_memories` 表
    3. 返回 top-K（默认 3 条）格式化文本
  - 实现 `save_memory_embedding()`：
    1. 每次 `save_message()` 调用时异步写入向量表
    2. 失败时降级：日志告警但不影响主流程
  - 集成到 `get_history(mode="hybrid")`：
    1. 近期 5 轮（10 条）从 Redis 获取
    2. 旧历史语义检索 top-3
    3. 合并返回格式化文本
  - 使用 tiktoken 精确计算 token

  **Must NOT do**:
  - 不阻塞主对话流程（embedding 写入失败不抛异常）
  - 不在每次对话时检索全量历史（仅检索超出滑动窗口的旧历史）

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: embedding API 调用 + pgvector 查询 + 降级策略
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 2 (with Tasks 7,9,10)
  - **Blocks**: Task 12 | **Blocked By**: Task 6 (HistoryManager), Task 3 (向量表)

  **References**:
  - `agent-service/app/knowledge/retriever.py` — 现有 embedding + pgvector 检索（复制模式）
  - `agent-service/app/core/history_manager.py` — Task 6 重构后的文件
  - `agent-service/app/config.py:48-50` — DashScope API 配置

  **Acceptance Criteria**:
  - [ ] TDD: `tests/test_memory/test_semantic_retrieval.py` → RED
  - [ ] query embedding 生成成功（DashScope API 返回 1024 维向量）
  - [ ] pgvector 余弦相似度检索返回 top-K 结果
  - [ ] embedding 写入失败时不影响主流程
  - [ ] tiktoken token 计数准确

  **QA Scenarios**:
  ```
  Scenario: 语义检索召回
    Tool: Bash (pytest)
    Preconditions: 历史中有 "Docker 部署" 相关对话
    Steps:
      1. 查询 "容器化部署"
      2. 检查语义检索结果包含 Docker 相关历史
    Expected Result: 语义相似历史被召回（非关键词匹配）
    Evidence: .sisyphus/evidence/task-8-semantic-recall.txt

  Scenario: Embedding 失败降级
    Tool: Bash (pytest)
    Steps:
      1. Mock DashScope API 返回错误
      2. 调用 save_memory_embedding()
      3. 检查不抛异常
    Expected Result: 日志告警，主流程继续
    Evidence: .sisyphus/evidence/task-8-fallback.txt
  ```

  **Commit**: YES
  - Message: `feat(memory): implement semantic retrieval pipeline for conversation history`
  - Files: `history_manager.py`, `tests/test_memory/test_semantic_retrieval.py`

- [x] 9. 路由集成测试 + 边界用例覆盖

  **What to do**:
  - 完善 `tests/test_routing/`：
    - `test_keywords.py` → GREEN（实现 Task 4 的关键词逻辑）
    - `test_edge_cases.py` — 边界用例：
      - 空消息、纯数字、纯 emoji
      - 超长消息（>500 字）
      - 混合意图（"帮我查一下 Docker，顺便上网搜最新版本"）
      - 英文问题（"How to deploy Hexo?"）
      - 特殊字符（URL、代码片段）
  - 确保 Orchestrator 和 ChatAgent 路由一致性
  - 补充 `chat.py` 中 SSE 事件完整性测试

  **Must NOT do**:
  - 不修改 Agent 内部逻辑（只写测试验证）

  **Recommended Agent Profile**: `unspecified-high`
  **Parallelization**: Wave 2 parallel | **Blocks**: Task 13 | **Blocked By**: Task 4

  **References**:
  - `agent-service/app/core/orchestrator.py` — 路由逻辑
  - `agent-service/app/agents/chat_agent.py` — 兜底路由

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_routing/ -v` → 所有测试 GREEN（15+ 用例）
  - [ ] 边界用例全覆盖

  **QA Scenarios**:
  ```
  Scenario: 全路由回归 → pytest tests/test_routing/ -v
    Expected Result: ALL PASS, 15+ cases
    Evidence: .sisyphus/evidence/task-9-routing-full.txt
  ```

  **Commit**: YES — `test(routing): add comprehensive routing edge case tests`
  - Files: `tests/test_routing/test_edge_cases.py`

- [x] 10. 老江湖人格集成测试 + 多轮一致性验证

  **What to do**:
  - 完善 `tests/test_chat/test_personality.py` → GREEN
  - 新增测试用例：
    - 人格一致性：10 轮对话后仍保持老江湖风格
    - 技术问题质量：人格不影响技术回答准确性
    - 边界场景：用户骂人 → 老江湖化解（不生气、幽默回应）
    - 边界场景：用户表白房间门 → 老江湖吃醋（幽默保护）
    - 边界场景：用户情绪低落 → 老江湖认真安慰
    - 边界场景：敏感话题 → 老江湖礼貌避开

  **Must NOT do**: 不修改 prompt（只测不改）

  **Recommended Agent Profile**: `unspecified-high`
  **Parallelization**: Wave 2 parallel | **Blocks**: Task 13 | **Blocked By**: Task 5

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_chat/ -v` → 8+ 测试 GREEN
  - [ ] 多轮对话人格一致性测试通过

  **QA Scenarios**:
  ```
  Scenario: 人格多轮一致性 → pytest test_personality.py
    Expected Result: 10 轮后仍用 eggegg + 自称老江湖
    Evidence: .sisyphus/evidence/task-10-consistency.txt
  ```

  **Commit**: YES — `test(chat): add personality consistency and edge case tests`
  - Files: `tests/test_chat/test_personality.py`

- [x] 11. OAuth 端到端流程联调

  **What to do**: E2E Playwright 测试完整 OAuth 流程，确认 GitHub OAuth App 配置正确
  **Recommended Agent Profile**: `deep` | **Parallelization**: Wave 3 (with 12,13,14)
  **Acceptance Criteria**: [ ] E2E 测试通过 [ ] 匿名↔GitHub 切换正常

  **QA Scenarios**:
  ```
  Scenario: 完整 OAuth 流程 → Playwright 点击按钮 → 模拟授权 → postMessage → 检查 UI
    Expected Result: 头像昵称正确显示
    Evidence: .sisyphus/evidence/task-11-e2e-oauth.png
  ```
  **Commit**: YES — `test(oauth): add E2E OAuth integration tests`

- [x] 12. 记忆模块端到端验证

  **What to do**: 验证完整记忆流程（对话→写入向量→多轮后召回），性能 < 200ms
  **Recommended Agent Profile**: `deep` | **Parallelization**: Wave 3 | **Blocked By**: Tasks 6,8
  **Acceptance Criteria**: [ ] 跨话题记忆召回正确 [ ] 延迟 < 200ms

  **QA Scenarios**:
  ```
  Scenario: 跨话题召回 → 聊 Docker → 聊 Hexo → 问"之前容器问题"
    Expected Result: 召回 Docker 历史
    Evidence: .sisyphus/evidence/task-12-cross-topic.txt
  ```
  **Commit**: YES — `test(memory): add E2E memory integration tests`

- [x] 13. 全路由回归 + 全量测试运行

  **What to do**: `pytest tests/ -v --cov=app` → 修复失败 → 覆盖率 > 60%
  **Recommended Agent Profile**: `unspecified-high` | **Parallelization**: Wave 3
  **Acceptance Criteria**: [ ] ALL 30+ 测试 PASS [ ] coverage > 60%

  **QA Scenarios**:
  ```
  Scenario: 全量测试 → pytest tests/ -v --cov=app
    Expected Result: ALL PASS, coverage > 60%
    Evidence: .sisyphus/evidence/task-13-full-coverage.txt
  ```
  **Commit**: NO（修复性提交）

- [x] 14. Docker 重建 + 博客前端同步

  **What to do**: rebuild Docker → healthy check → sync widget 文件到博客 + hexo-widget
  **Recommended Agent Profile**: `quick` | **Parallelization**: Wave 3 | **Blocked By**: Task 7
  **Acceptance Criteria**: [ ] 容器 healthy [ ] 博客文件已更新

  **QA Scenarios**:
  ```
  Scenario: 部署验证 → curl /health → ls blog/source/js/agent-widget.js
    Expected Result: {"status":"healthy"}, 文件存在
    Evidence: .sisyphus/evidence/task-14-deploy.txt
  ```
  **Commit**: YES — `chore: rebuild Docker and sync blog frontend`

---

- [ ] F1. **Plan Compliance Audit** — `oracle`
- [ ] F2. **Code Quality Review** — `unspecified-high`
- [ ] F3. **Real Manual QA** — `unspecified-high`
- [ ] F4. **Scope Fidelity Check** — `deep`

---

## Commit Strategy

- **Wave 0**: `chore(test): setup pytest infrastructure` - tests/conftest.py, requirements-dev.txt
- **Wave 1**: `feat: OAuth callback, memory schema, routing merge, personality prompt`
- **Wave 2**: `feat: OAuth frontend, memory retrieval, routing tests, personality tests`
- **Wave 3**: `feat: E2E integration, Docker rebuild, blog sync`

---

## Success Criteria

### Verification Commands
```bash
pytest tests/ -v                    # Expected: all tests pass
curl http://localhost:8001/health   # Expected: {"status":"healthy"}
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass
- [ ] Docker container healthy
- [ ] Blog frontend synced
