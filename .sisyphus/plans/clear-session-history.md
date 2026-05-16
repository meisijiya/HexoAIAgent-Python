# 清除历史会话功能 + 会话自动过期

## TL;DR

> **Quick Summary**: 后端新增 DELETE API 软删除会话数据（Redis + PG），前端顶部工具栏增加清除按钮；同时新增定时任务——每日凌晨自动软删除 30 天无活动会话，7 天后物理清除。
> 
> **Deliverables**:
> - `DELETE /api/chat/session/{id}` 端点（含所有权校验）
> - 数据库迁移：Message/Session/ConversationMemory 三表加字段
> - 定时清理任务（FastAPI lifespan + asyncio）
> - 前端清除按钮 + 自动新会话流程
> - 现有查询全部过滤 `deleted_at IS NULL`
> 
> **Estimated Effort**: Medium
> **Parallel Execution**: YES - 2 waves
> **Critical Path**: Task 1-3（模型迁移）→ Task 6（DELETE API）→ Task 9-10（前端）

---

## Context

### Original Request
用户要求新增"清除历史会话"功能：前端点击清除按钮 → 后端清除该 session 的 Redis 数据 + PG 逻辑删除 → 前端清空 localStorage 并自动开始新会话。另外，定时任务每天凌晨扫描 30 天无活动的会话，自动软删除。

### Interview Summary
**Key Discussions**:
- **软删除策略**：`deleted_at TIMESTAMP NULL`，NOT BOOLEAN，便于追溯和定时清理
- **后悔窗口**：标记后 7 天物理删除
- **自动过期**：30 天无活动（`last_active_at < NOW() - 30天`）自动软删除
- **清除按钮**：顶部工具栏，清后自动新会话
- **定时任务**：FastAPI lifespan + asyncio sleep-until-midnight 模式
- **测试**：仅 Agent QA，不写单元测试

**Research Findings**:
- Redis keys：`session:{id}:context`（List）、`round_counter:{id}`（int）、`rate:{user_id}`（不清）
- `agent_messages` 继承 BaseModel（有 updated_at），`conversation_memories` 继承 Base（无 updated_at）
- `Session.updated_at` 虽有 `onupdate`，但发消息时未显式触发更新
- 前端 sessionId 存 `localStorage.hexo_agent_session`，首次请求 session_id=null 时后端自动创建

### Metis Review
**Identified Gaps** (addressed):
- **🔴 安全缺口**：DELETE API 必须校验 `session.user_id == token_user_id`（同 chat.py:73-78 模式）
- **🔴 查询遗漏**：`get_sessions`、`get_messages`、`_semantic_search` 三处查询需过滤 `deleted_at`
- **🟡 模型差异**：`ConversationMemory` 不继承 BaseModel，需单独加 `deleted_at`
- **🟡 缓存一致**：RedSet `user:{id}:sessions` 需失效
- **🟡 调度容错**：asyncio.create_task crash 后需有重试机制（全局标志位 + Event）

---

## Work Objectives

### Core Objective
实现会话级别的“清除历史”功能，支持手动清除（前端按钮）和自动过期（30 天无活动），Redis 与 PostgreSQL 数据保持一致。

### Concrete Deliverables
- `DELETE /api/chat/session/{session_id}` API 端点
- `agent_messages`、`conversation_memories` 新增 `deleted_at` 列
- `agent_sessions` 新增 `last_active_at` 列
- chat API 每次发消息时更新 `session.last_active_at`
- 定时清理任务（lifespan 内 asyncio task）
- 所有现有查询（get_sessions, get_messages, semantic_search, get_history）过滤 `deleted_at`
- 前端工具栏新增 🗑️ 按钮
- hexo-widget 同步

### Definition of Done
- [ ] `curl -X DELETE /api/chat/session/{id}?token=xxx` → 200 + Redis 已清除 + PG 已标记
- [ ] `GET /api/chat/sessions?token=xxx` → 不返回已清除的会话
- [ ] `GET /api/chat/sessions/{id}/messages?token=xxx` → 不返回标记 deleted 的消息
- [ ] 定时任务运行后：已软删除 > 7 天的记录消失；30 天无活动会话被软删除
- [ ] 前端点清除 → localStorage 清空 → 下次发消息时 session_id=null → 新会话创建

### Must Have
- DELETE API 所有权校验（session.user_id == user_id）
- 软删除原子化（同一请求内 Redis + PG 都完成）
- deleted_at IS NULL 过滤覆盖所有读查询
- 定时任务异常恢复（crash 后重建）

### Must NOT Have (Guardrails)
- ❌ 不清除 `rate:{user_id}` 限流键
- ❌ 不清除其他用户的会话（所有权隔离）
- ❌ 删除操作不物理删除 agent_sessions 表记录
- ❌ 定时任务不引入 APScheduler/Celery 等外部调度
- ❌ 不修改 knowledge_agent/search_agent 的存储逻辑

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: NO
- **Automated tests**: None
- **Framework**: N/A
- **Agent-Executed QA**: ALWAYS (curl for API, Playwright for frontend)

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **API/Backend**: Use Bash (curl) - Send requests, assert status + response fields + DB state
- **Frontend/UI**: Use Playwright - Navigate, click button, assert DOM changes
- **Scheduler**: Use Bash - Check DB state before/after simulated cleanup

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately - 模型迁移 + 基础设施):
├── Task 1: Message 模型加 deleted_at [quick]
├── Task 2: ConversationMemory 模型加 deleted_at [quick]
├── Task 3: Session 模型加 last_active_at [quick]
├── Task 4: Redis 会话清理工具函数 [quick]
└── Task 5: chat handler 更新 last_active_at [quick]

Wave 2 (After Wave 1 - 核心 API + 查询过滤):
├── Task 6: DELETE /api/chat/session/{id} 端点 [deep]
├── Task 7: 所有查询过滤 deleted_at [deep]
└── Task 8: 定时清理任务 lifespan [deep]

Wave 3 (After Wave 2 - 前端):
├── Task 9: 前端清除按钮 + 清除逻辑 [visual-engineering]
├── Task 10: hexo-widget 同步 [visual-engineering]
└── Task 11: 数据库迁移执行 [quick]

FINAL (After ALL tasks):
├── F1: Plan compliance audit [oracle]
├── F2: Code quality review [unspecified-high]
├── F3: Real manual QA [unspecified-high]
└── F4: Scope fidelity check [deep]
```

Critical Path: Task 1-3 → Task 6 → Task 7 → Task 8 → Task 9-10
Max Concurrent: 5 (Wave 1)

---

## TODOs

- [x] 1. Message 模型加 `deleted_at` 字段

  **What to do**:
  - 在 `app/models/message.py` 的 `Message` 类中加 `deleted_at = Column(DateTime, nullable=True, default=None, comment="软删除时间")`
  - 导入 `DateTime`：`from sqlalchemy import Column, String, Text, ForeignKey, DateTime`
  - `Message` 继承 `BaseModel`，`BaseModel` 已有 `created_at`/`updated_at`，所以 `DateTime` 可能需要追加到 import
  - 不需修改 BaseModel——其他表不需要 deleted_at
  - 验证：重启服务后 `SELECT column_name FROM information_schema.columns WHERE table_name='agent_messages'` 能看到 `deleted_at`

  **Must NOT do**:
  - 不要设 `nullable=False`（会导致现有数据报错）
  - 不要加 `default=datetime.utcnow`（新记录应 NULL）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 单文件小改动，加一个字段，风险低
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 2, 3, 4)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 6 (DELETE API needs deleted_at), Task 7 (query filters)
  - **Blocked By**: None

  **References**:
  - `app/models/message.py:6` - 现有 import，需追加 `DateTime`
  - `app/models/message.py:20-28` - Message 类定义位置，在 role/content 等字段后加
  - `app/models/base.py:32-45` - created_at/updated_at 模式参考

  **Acceptance Criteria**:
  - [ ] `Message` 类有 `deleted_at = Column(DateTime, nullable=True, default=None)`
  - [ ] `docker compose up -d --build agent-service` 成功，无迁移错误
  - [ ] 现有消息 `deleted_at` 为 NULL（数据不丢失）

  **QA Scenarios**:

  ```
  Scenario: 新消息创建时 deleted_at 为 NULL
    Tool: Bash (curl + psql)
    Preconditions: 服务运行中，有有效 token
    Steps:
      1. curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{"message":"test","token":"VALID_TOKEN"}' 2>&1 | head -5
      2. docker exec hexo-postgres psql -U agent -d agent_db -c "SELECT deleted_at FROM agent_messages ORDER BY created_at DESC LIMIT 1;"
      3. Assert: deleted_at 列存在且值为 NULL
    Expected Result: 新增消息的 deleted_at 为 NULL（空行）
    Evidence: .sisyphus/evidence/task-1-deleted-at-null.txt

  Scenario: 旧数据迁移不丢失
    Tool: Bash (psql)
    Preconditions: agent_messages 表已有数据
    Steps:
      1. docker exec hexo-postgres psql -U agent -d agent_db -c "SELECT COUNT(*) FROM agent_messages WHERE deleted_at IS NULL;"
      2. docker exec hexo-postgres psql -U agent -d agent_db -c "SELECT COUNT(*) FROM agent_messages;"
      3. Assert: 两个 COUNT 相等（全部旧数据 deleted_at=NULL）
    Expected Result: 旧数据全部保留，deleted_at 为 NULL
    Evidence: .sisyphus/evidence/task-1-migration-safe.txt
  ```

  **Commit**: YES (groups with Task 2-3)
  - Message: `feat(db): add deleted_at to Message and ConversationMemory, last_active_at to Session`
  - Files: `app/models/message.py`

- [x] 2. ConversationMemory 模型加 `deleted_at` 字段

  **What to do**:
  - 在 `app/models/memory.py` 的 `ConversationMemory` 类中加 `deleted_at = Column(DateTime, nullable=True, default=None, comment="软删除时间")`
  - `ConversationMemory` 继承裸 `Base`（非 BaseModel），所以需单独加 `DateTime` import
  - 已有 `from datetime import datetime`，不需要额外导入
  - 放在 `created_at` 字段之后

  **Must NOT do**:
  - 不要让 ConversationMemory 改继承 BaseModel（会引入不必要的 UUID id 和 updated_at）
  - 不要设 `nullable=False`

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 单字段追加，与 Task 1 同类型
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 1, 3, 4)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 6, Task 7
  - **Blocked By**: None

  **References**:
  - `app/models/memory.py:6` - 现有 import 行
  - `app/models/memory.py:68-74` - created_at 字段位置，在其后加 deleted_at
  - `app/models/memory.py:14-82` - 完整类定义

  **Acceptance Criteria**:
  - [ ] `ConversationMemory` 类有 `deleted_at = Column(DateTime, nullable=True, default=None)`
  - [ ] 服务重启正常
  - [ ] `SELECT deleted_at FROM conversation_memories LIMIT 1` 返回 NULL

  **QA Scenarios**:

  ```
  Scenario: 新批次记忆 created 后 deleted_at 为 NULL
    Tool: Bash (curl + psql)
    Preconditions: 服务运行，有活跃会话（已发 5+ 轮消息触发批次）
    Steps:
      1. 发 5 轮消息触发批次 embedding
      2. docker exec hexo-postgres psql -U agent -d agent_db -c "SELECT deleted_at FROM conversation_memories ORDER BY created_at DESC LIMIT 3;"
      3. Assert: 所有新记录的 deleted_at 均为 NULL
    Expected Result: 3 行均显示空值
    Evidence: .sisyphus/evidence/task-2-memory-null.txt
  ```

  **Commit**: YES (groups with Task 1, 3)
  - Files: `app/models/memory.py`

- [x] 3. Session 模型加 `last_active_at` 字段

  **What to do**:
  - 在 `app/models/session.py` 的 `Session` 类中加 `last_active_at = Column(DateTime, nullable=True, default=None, comment="最后活跃时间")`
  - `Session` 继承 `BaseModel`，需追加 `DateTime` import：`from sqlalchemy import Column, String, ForeignKey, DateTime`
  - 放在 `title` 字段之后

  **Must NOT do**:
  - 不要复用 `updated_at`（它依赖 SQLAlchemy onupdate，发消息时不会触发）
  - 不要设 `default=datetime.utcnow`（新会话首次消息时才设置）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 单字段追加
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 1, 2, 4)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 5, Task 8
  - **Blocked By**: None

  **References**:
  - `app/models/session.py:6-8` - 现有 import
  - `app/models/session.py:30-35` - title 字段，在其后加 last_active_at

  **Acceptance Criteria**:
  - [ ] `Session` 类有 `last_active_at = Column(DateTime, nullable=True, default=None)`
  - [ ] 服务重启正常

  **QA Scenarios**:

  ```
  Scenario: 新会话创建时 last_active_at 为 NULL
    Tool: Bash (psql)
    Preconditions: 服务运行
    Steps:
      1. docker exec hexo-postgres psql -U agent -d agent_db -c "SELECT last_active_at FROM agent_sessions ORDER BY created_at DESC LIMIT 1;"
      2. Assert: 最新会话的 last_active_at 为 NULL（或为刚创建时的时间）
    Expected Result: 字段存在，值可空
    Evidence: .sisyphus/evidence/task-3-last-active.txt
  ```

  **Commit**: YES (groups with Task 1, 2)
  - Files: `app/models/session.py`

- [x] 4. Redis 会话清理工具函数

  **What to do**:
  - 在 `app/core/redis.py` 末尾新增 `async def clear_session_redis(session_id: str) -> dict`
  - 函数逻辑：
    1. `await redis_client.delete(f"session:{session_id}:context")`
    2. `await redis_client.delete(f"round_counter:{session_id}")`
    3. 失效用户会话缓存：扫描 `user:*:sessions` 模式，删除对应 key 或标记失效
    4. 返回 `{"context_deleted": bool, "counter_deleted": bool}`
  - 使用 `from app.core.redis import get_redis` 获取连接
  - 错误处理：单个 key 删除失败不阻塞其他，记录 logger.warning

  **Must NOT do**:
  - 不要删除 `rate:{user_id}` 限流键
  - 不要删除 `embedding:*` 知识库缓存

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 简单 Redis 操作封装，无外部依赖
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 1, 2, 3, 5)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 6 (DELETE API calls this)
  - **Blocked By**: None

  **References**:
  - `app/core/redis.py:83-140` - 现有 session context 读写模式
  - `app/core/redis.py:21-45` - Redis 连接获取方式
  - `app/api/chat.py:176` - `round_counter:{session_id}` key 格式

  **Acceptance Criteria**:
  - [ ] `clear_session_redis(session_id)` 函数存在且可导入
  - [ ] 调用后 `redis_client.exists(f"session:{id}:context")` 返回 0
  - [ ] 调用后 `redis_client.exists(f"round_counter:{id}")` 返回 0
  - [ ] rate:{user_id} 不受影响

  **QA Scenarios**:

  ```
  Scenario: 清除 Redis 数据后 key 不存在
    Tool: Bash (docker exec redis-cli)
    Preconditions: 某会话有活跃 Redis 数据（发过消息）
    Steps:
      1. docker exec hexo-redis redis-cli EXISTS "session:{SESSION_ID}:context"
      2. docker exec hexo-redis redis-cli EXISTS "round_counter:{SESSION_ID}"
      3. 触发清理（后续 Task 6 调用）
      4. docker exec hexo-redis redis-cli EXISTS "session:{SESSION_ID}:context"
      5. Assert: Step 4 返回 0（key 已删除）
    Expected Result: 清理后两个 key 均不存在
    Evidence: .sisyphus/evidence/task-4-redis-cleared.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Files: `app/core/redis.py`

- [x] 5. chat handler 每次发消息更新 `session.last_active_at`

  **What to do**:
  - 在 `app/api/chat.py` 的 chat 端点中，验证会话存在后（第 79 行之后），加一行：
    `session.last_active_at = datetime.utcnow()`
  - 需要 `from datetime import datetime`（检查是否已 import）
  - 同时 `import` 处确认 Session 模型的 last_active_at 可访问
  - 这个更新会随着后续的 `db.commit()` 一起持久化（第 165 行已有 commit）

  **Must NOT do**:
  - 不要在新建会话时设置（新建会话下次发消息才设）
  - 不要额外创建 commit（复用已有 commit）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 单行代码改动
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 1-4)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 8 (scheduler relies on last_active_at being updated)
  - **Blocked By**: Task 3 (Session model must have last_active_at)

  **References**:
  - `app/api/chat.py:72-81` - 会话验证逻辑，在此处加 last_active_at 更新
  - `app/api/chat.py:1-10` - 顶部 import，检查 datetime
  - `app/models/session.py:13-42` - Session 类定义

  **Acceptance Criteria**:
  - [ ] 发消息后 `SELECT last_active_at FROM agent_sessions WHERE id='...'` 返回最新时间
  - [ ] 新建会话首次发消息时 last_active_at 从 NULL 变为有值

  **QA Scenarios**:

  ```
  Scenario: 发消息后 last_active_at 更新
    Tool: Bash (curl + psql)
    Preconditions: 已有会话 SESSION_ID，last_active_at 为旧值或 NULL
    Steps:
      1. docker exec hexo-postgres psql -U agent -d agent_db -c "SELECT last_active_at FROM agent_sessions WHERE id='{SESSION_ID}';"
      2. curl -X POST http://localhost:8000/api/chat -d '{"message":"ping","session_id":"{SESSION_ID}","token":"VALID"}'
      3. sleep 3
      4. docker exec hexo-postgres psql -U agent -d agent_db -c "SELECT last_active_at FROM agent_sessions WHERE id='{SESSION_ID}';"
      5. Assert: Step 4 时间 > Step 1 时间（或从 NULL 变成有值）
    Expected Result: last_active_at 更新为当前时间
    Evidence: .sisyphus/evidence/task-5-last-active-updated.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Files: `app/api/chat.py`

---

- [x] 6. DELETE /api/chat/session/{session_id} 端点

  **What to do**:
  - 在 `app/api/chat.py` 新增路由：`@router.delete("/session/{session_id}")`
  - **权限校验**（Metis 安全缺口）：
    1. `user_id = verify_token(token)` — 无效 token → 401
    2. 查 Session：`select(Session).where(Session.id == session_id, Session.user_id == user_id)`
    3. 不存在 → 404；存在但不属当前用户 → 403
  - **原子操作**（try/except 包裹）：
    1. Redis：`await clear_session_redis(session_id)`（Task 4 函数）
    2. PG messages：`update(Message).where(Message.session_id == sid, Message.deleted_at == None).values(deleted_at=datetime.utcnow())`
    3. PG memories：`update(ConversationMemory).where(ConversationMemory.session_id == sid, ConversationMemory.deleted_at == None).values(deleted_at=datetime.utcnow())`
    4. 标记 session：`session.last_active_at = None`
    5. `await db.commit()`
  - 返回：`{"ok": True, "deleted_messages": N, "deleted_memories": M}`
  - 异常 → `await db.rollback()` → 500

  **Must NOT do**:
  - 不要物理删除 `agent_sessions` 行
  - 不要忘记 rollback

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 多步原子操作 + 权限校验 + 错误回滚
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 7)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 9 (前端调用此 API)
  - **Blocked By**: Task 1, 2, 4

  **References**:
  - `app/api/chat.py:35-81` - POST /api/chat，参考 token 验证 + session 查询模式
  - `app/api/chat.py:223-243` - GET /sessions 端点
  - `app/core/redis.py` (Task 4) - `clear_session_redis()`
  - `app/api/chat.py:72-81` - `Session.user_id == user_id` 所有权校验

  **Acceptance Criteria**:
  - [ ] `DELETE /api/chat/session/{id}?token=xxx` → 200
  - [ ] 另一用户 token → 403/404
  - [ ] 删除后 Redis key 不存在
  - [ ] 删除后 PG 中对应记录 `deleted_at IS NOT NULL`

  **QA Scenarios**:

  ```
  Scenario: 正常清除会话
    Tool: Bash (curl)
    Preconditions: 已有会话 SID，有 3+ 条消息
    Steps:
      1. curl -X DELETE "http://localhost:8000/api/chat/session/{SID}?token={TOKEN}" | jq .
      2. Assert: HTTP 200, .ok==true, .deleted_messages>=3
      3. docker exec hexo-redis redis-cli EXISTS "session:{SID}:context"
      4. Assert: 返回 0
      5. docker exec hexo-postgres psql -U agent -d agent_db -c "SELECT COUNT(*) FROM agent_messages WHERE session_id='{SID}' AND deleted_at IS NOT NULL;"
      6. Assert: count >= 3
    Expected Result: API 200 + Redis 清空 + PG 全部标记
    Evidence: .sisyphus/evidence/task-6-delete-success.txt

  Scenario: 权限校验 - 另一用户无法删除
    Tool: Bash (curl)
    Preconditions: 用户 A 的会话 SID_A，用户 B 的 token TOKEN_B
    Steps:
      1. curl -s -o /dev/null -w "%{http_code}" -X DELETE "http://localhost:8000/api/chat/session/{SID_A}?token={TOKEN_B}"
      2. Assert: 输出 403 或 404（非 200）
    Expected Result: 拒绝访问
    Evidence: .sisyphus/evidence/task-6-auth-check.txt
  ```

  **Commit**: YES
  - Message: `feat(api): add DELETE /api/chat/session/{id} with auth check`
  - Files: `app/api/chat.py`

- [x] 7. 所有现有查询过滤 `deleted_at IS NULL`

  **What to do**:
  - 修改 3 个查询点，全部加 `.where(Model.deleted_at == None)`：
    1. **`GET /sessions/{id}/messages`** (`chat.py:246+`)：`select(Message).where(session_id=...)` → 加 `where(Message.deleted_at == None)`
    2. **`history_manager._semantic_search()`** (`history_manager.py:271-277`)：`select(ConversationMemory).where(session_id=...)` → 加 `where(ConversationMemory.deleted_at == None)`
    3. **`chat_agent.get_history()`** (`chat_agent.py:150-170`)：`select(Message).where(session_id=...)` → 加 `where(Message.deleted_at == None)`
  - Sessions 列表（`GET /api/chat/sessions`）不变——`agent_sessions` 表不软删除

  **Must NOT do**:
  - 不要改动功能逻辑，只加 WHERE 条件
  - 不要修改 knowledge.py / search_agent.py

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 跨 3 文件查询修改，需确保不漏
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 6)
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: Task 1, 2

  **References**:
  - `app/api/chat.py:246-260` - get_messages
  - `app/core/history_manager.py:271-277` - _semantic_search
  - `app/agents/chat_agent.py:150-170` - get_history

  **Acceptance Criteria**:
  - [ ] `GET /sessions/{id}/messages` 不返回已软删除消息
  - [ ] `_semantic_search()` 不返回已软删除记忆
  - [ ] `get_history()` 不返回已软删除消息

  **QA Scenarios**:

  ```
  Scenario: 清除后消息列表为空
    Tool: Bash (curl)
    Preconditions: 某会话已通过 DELETE 清除
    Steps:
      1. curl "http://localhost:8000/api/chat/sessions/{SID}/messages?token={TOKEN}" | jq '. | length'
      2. Assert: 输出 0
    Expected Result: 空数组
    Evidence: .sisyphus/evidence/task-7-messages-filtered.txt

  Scenario: 清除后语义检索不召回旧记忆
    Tool: Bash (curl)
    Preconditions: 已清除的会话
    Steps:
      1. curl -N -X POST http://localhost:8000/api/chat -d '{"message":"记得之前吗","session_id":"{SID}","token":"{TOKEN}"}' 2>&1 | grep semantic_recall
      2. Assert: 无输出 或 count=0
    Expected Result: 不召回已删除记忆
    Evidence: .sisyphus/evidence/task-7-semantic-filtered.txt
  ```

  **Commit**: YES (groups with Task 6)
  - Message: `fix(query): filter deleted_at IS NULL in all session queries`
  - Files: `app/api/chat.py`, `app/core/history_manager.py`, `app/agents/chat_agent.py`

- [x] 8. 定时清理任务（lifespan + asyncio）

  **What to do**:
  - 新建 `app/core/cleanup.py`，核心函数：
    ```python
    async def run_cleanup():
        """执行一次清理：① 30天过期 → 软删除 ② 7天软删除 → 物理删除"""
        from app.core.database import async_session_maker
        from sqlalchemy import update, delete
        async with async_session_maker() as db:
            # ① 自动过期：30天无活动
            cutoff_30d = datetime.utcnow() - timedelta(days=30)
            result = await db.execute(
                select(Session.id).where(
                    Session.last_active_at < cutoff_30d,
                    Session.last_active_at != None
                )
            )
            for sid in [row[0] for row in result.all()]:
                await db.execute(update(Message).where(
                    Message.session_id == sid, Message.deleted_at == None
                ).values(deleted_at=datetime.utcnow()))
                await db.execute(update(ConversationMemory).where(
                    ConversationMemory.session_id == sid, ConversationMemory.deleted_at == None
                ).values(deleted_at=datetime.utcnow()))
            # ② 物理删除：软删除 > 7天
            cutoff_7d = datetime.utcnow() - timedelta(days=7)
            await db.execute(delete(Message).where(Message.deleted_at < cutoff_7d))
            await db.execute(delete(ConversationMemory).where(ConversationMemory.deleted_at < cutoff_7d))
            await db.commit()
    ```
  - 在 `main.py` lifespan 启动阶段：`asyncio.create_task(_cleanup_loop())`（带 sleep-until-3am + 全局标志位防重复）
  - 关闭阶段：`task.cancel()`
  - 异常处理：try/except 包裹，出错记 log 继续

  **Must NOT do**:
  - 不要删除 agent_sessions 表记录
  - 不要引入 APScheduler/Celery

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 异步调度 + 多表事务 + 异常恢复
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 7)
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: Task 3, 5

  **References**:
  - `app/main.py:29-53` - lifespan 模式
  - `app/core/database.py` - `async_session_maker`
  - `app/models/session.py` - Session.id

  **Acceptance Criteria**:
  - [ ] `cleanup.py` 存在，函数可调用
  - [ ] 模拟 7天前软删除 → 物理删除
  - [ ] 模拟 30天无活动 → 自动标记软删除
  - [ ] 服务重启不创建多个 task

  **QA Scenarios**:

  ```
  Scenario: 物理删除 >7天的软删除记录
    Tool: Bash (psql + python)
    Preconditions: 插入 deleted_at='2020-01-01' 的测试记录
    Steps:
      1. psql: INSERT INTO agent_messages (...) VALUES (...,'2020-01-01')
      2. docker exec agent-service python -c "import asyncio;from app.core.cleanup import run_cleanup;asyncio.run(run_cleanup())"
      3. psql: SELECT COUNT(*) FROM agent_messages WHERE deleted_at='2020-01-01'
      4. Assert: count = 0
    Expected Result: 物理删除
    Evidence: .sisyphus/evidence/task-8-physical-delete.txt

  Scenario: 30天无活动自动软删除
    Tool: Bash (psql + python)
    Preconditions: 某会话 last_active_at='2020-01-01'
    Steps:
      1. psql: UPDATE agent_sessions SET last_active_at='2020-01-01' WHERE id='{OLD_SID}'
      2. 运行 run_cleanup()
      3. psql: SELECT COUNT(*) FROM agent_messages WHERE session_id='{OLD_SID}' AND deleted_at IS NOT NULL
      4. Assert: count > 0
    Expected Result: 过期会话数据被标记
    Evidence: .sisyphus/evidence/task-8-auto-expire.txt
  ```

  **Commit**: YES
  - Message: `feat(scheduler): add daily cleanup for expired sessions`
  - Files: `app/core/cleanup.py`, `app/main.py`

---

- [x] 9. 前端清除按钮 + 清除逻辑

  **What to do**:
  - 在 `agent-widget.js` 的 `createWidget()` 中，工具栏（header）新增清除按钮：
    ```html
    <button onclick="clearSession()" title="清除会话" class="hexo-agent-clear-btn">🗑️</button>
    ```
  - 新增 `async function clearSession()`：
    1. 确认弹窗：`confirm("确定清除当前会话？数据将在一周后彻底删除。")`
    2. 调 API：`fetch(DELETE /api/chat/session/{state.sessionId}?token={state.token})`
    3. 成功后：清 `localStorage.hexo_agent_session`，重置 `state.sessionId = null`
    4. 清空聊天面板：`$('#agentMessages').innerHTML = ''`
    5. 显示提示："会话已清除，下次发送消息将自动开始新对话"
    6. 调用 `saveState()` 持久化
  - CSS：`.hexo-agent-clear-btn` 样式——hover 红色，与工具栏其他按钮对齐
  - 失败处理：API 返回非 200 → alert("清除失败：" + 错误信息)

  **Must NOT do**:
  - 不要删除 rate limit 相关 localStorage 数据
  - 不要触发页面刷新

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: 前端 UI 按钮 + JS 交互逻辑 + CSS 样式
  - **Skills**: `["playwright"]`
    - `playwright`: 用于 QA 场景验证 UI 交互

  **Parallelization**:
  - **Can Run In Parallel**: NO（依赖 Task 6 API 可用）
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 10（hexo-widget 同步）
  - **Blocked By**: Task 6

  **References**:
  - `app/static/agent-widget.js:460-470` - `handleLogout()` 清 localStorage 模式
  - `app/static/agent-widget.js:140-155` - `sendMessage()` API 调用模式
  - `app/static/agent-widget.js:690-703` - `state.sessionId` 设置
  - `app/static/agent-widget.css` - 现有按钮样式参考

  **Acceptance Criteria**:
  - [ ] 工具栏显示 🗑️ 按钮
  - [ ] 点击 → 确认弹窗 → API 调用 → 清除 localStorage → 清空消息
  - [ ] 清除后发消息 → 新会话创建（session_id=null）
  - [ ] CSS hover 变红

  **QA Scenarios**:

  ```
  Scenario: 点击清除按钮完成清除
    Tool: Playwright
    Preconditions: 页面已加载 agent-widget，有活跃会话和消息
    Steps:
      1. page.goto('http://localhost:8000')
      2. page.click('.hexo-agent-clear-btn')
      3. dialog = page.waitForEvent('dialog'); dialog.accept()
      4. page.waitForSelector('.hexo-agent-message', {state: 'detached'}) 或检查消息区为空
      5. const sid = page.evaluate(() => localStorage.getItem('hexo_agent_session'))
      6. Assert: sid === null 或 undefined
    Expected Result: 按钮可用，确认后清理完成
    Failure Indicators: API 报错 / localStorage 未清除 / 消息残留
    Evidence: .sisyphus/evidence/task-9-clear-button.png

  Scenario: 清除后发消息创建新会话
    Tool: Playwright
    Preconditions: 刚完成清除
    Steps:
      1. page.fill('#agentInput', '新会话测试')
      2. page.click('#agentSendBtn')
      3. page.waitForSelector('.hexo-agent-message.assistant', {timeout: 15000})
      4. const newSid = page.evaluate(() => localStorage.getItem('hexo_agent_session'))
      5. const oldSid = '{PREVIOUS_SESSION_ID}'
      6. Assert: newSid !== oldSid && newSid !== null
    Expected Result: 新会话自动创建，sessionId 更新
    Evidence: .sisyphus/evidence/task-9-new-session.png
  ```

  **Commit**: YES
  - Message: `feat(ui): add clear session button with auto-new-session`
  - Files: `app/static/agent-widget.js`, `app/static/agent-widget.css`

- [x] 10. hexo-widget 同步

  **What to do**:
  - 复制 Task 9 所有改动到 hexo-widget 目录：
    - `hexo-widget/source/js/agent-widget.js` ← `app/static/agent-widget.js`
    - `hexo-widget/source/css/agent-widget.css` ← `app/static/agent-widget.css`
  - 也同步到博客主题目录：
    - `/mnt/c/Users/22923/Desktop/blog/themes/Chic/source/js/agent-widget.js`
    - `/mnt/c/Users/22923/Desktop/blog/themes/Chic/source/css/agent-widget.css`
  - 简单 cp 即可，无需改动

  **Must NOT do**:
  - 不要修改 hexo-widget 的构建配置

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 纯文件复制，无逻辑变更
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: Task 9

  **References**:
  - `app/static/agent-widget.js` - 源文件
  - `hexo-widget/source/js/agent-widget.js` - 目标
  - `/mnt/c/Users/22923/Desktop/blog/themes/Chic/source/js/agent-widget.js` - 博客主题目标

  **Acceptance Criteria**:
  - [ ] 三处 widget 文件内容一致
  - [ ] hexo-widget 构建无报错

  **QA Scenarios**:

  ```
  Scenario: 文件同步一致性
    Tool: Bash (diff)
    Preconditions: Task 9 已完成
    Steps:
      1. diff app/static/agent-widget.js hexo-widget/source/js/agent-widget.js
      2. Assert: 无差异（或仅路径相关差异）
      3. diff app/static/agent-widget.css hexo-widget/source/css/agent-widget.css
      4. Assert: 无差异
    Expected Result: 三处文件内容一致
    Evidence: .sisyphus/evidence/task-10-diff-output.txt
  ```

  **Commit**: YES (groups with Task 9)
  - Message: `chore: sync agent-widget to hexo-widget and blog theme`
  - Files: `hexo-widget/source/js/agent-widget.js`, `hexo-widget/source/css/agent-widget.css`

- [x] 11. 数据库迁移执行

  **What to do**:
  - 不需要单独迁移脚本——SQLAlchemy 在 `init_db()` 中 `Base.metadata.create_all` 会自动加列（`nullable=True` 新列安全）
  - 但仍需验证：`docker compose down && docker compose up -d --build` 后：
    1. `agent_messages` 有 `deleted_at` 列
    2. `conversation_memories` 有 `deleted_at` 列
    3. `agent_sessions` 有 `last_active_at` 列
  - 验证命令：
    ```sql
    SELECT column_name FROM information_schema.columns WHERE table_name='agent_messages' AND column_name='deleted_at';
    SELECT column_name FROM information_schema.columns WHERE table_name='conversation_memories' AND column_name='deleted_at';
    SELECT column_name FROM information_schema.columns WHERE table_name='agent_sessions' AND column_name='last_active_at';
    ```

  **Must NOT do**:
  - 不要手动写 SQL migration（SQLAlchemy auto-DDL 足够）
  - 不要 drop 重建表

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 重建验证，无代码改动
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO（依赖所有模型改动完成）
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: Task 1, 2, 3

  **References**:
  - `app/core/database.py` - `init_db()` 函数
  - `docker-compose.yml` - 服务定义

  **Acceptance Criteria**:
  - [ ] `docker compose up -d --build` 成功
  - [ ] 三个新列存在
  - [ ] 现有数据未丢失

  **QA Scenarios**:

  ```
  Scenario: 迁移后服务正常运行
    Tool: Bash (docker compose + psql)
    Preconditions: 代码已修改
    Steps:
      1. docker compose up -d --build agent-service 2>&1 | tail -5
      2. sleep 5
      3. curl http://localhost:8000/health | jq .status
      4. Assert: "healthy"
      5. 逐一检查三个新列
    Expected Result: 服务健康，三列存在
    Evidence: .sisyphus/evidence/task-11-migration-verify.txt
  ```

  **Commit**: NO（验证性任务，不产生代码改动）

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. Verify: Must Have (DELETE auth check, atomicity, query filters, scheduler recovery) all present. Search for Must NOT Have violations. Check evidence files exist in .sisyphus/evidence/.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `docker compose build agent-service`. Review all changed files for: `as any`/`@ts-ignore`, empty catches, console.log in prod, commented-out code, unused imports. Check AI slop.
  Output: `Build [PASS/FAIL] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high` (+ `playwright` skill)
  Start from clean state. Test: ① curl DELETE → verify Redis cleared + PG deleted_at set. ② curl GET sessions → verify deleted session not in list. ③ curl GET messages → verify empty. ④ Playwright: click clear button → verify localStorage cleared → send message → verify new session created. ⑤ Simulate scheduler: manually set deleted_at < 7 days ago → run cleanup → verify physical delete.
  Output: `Scenarios [N/N pass] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was built, nothing beyond spec. Check "Must NOT do" compliance. Detect cross-task contamination.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Wave 1**: `feat(db): add deleted_at and last_active_at fields` - models/*.py
- **Wave 2**: `feat(api): add DELETE session endpoint + cleanup scheduler` - api/chat.py, main.py
- **Wave 3**: `feat(ui): add clear session button with auto-new-session` - static/agent-widget.*

---

## Success Criteria

### Verification Commands
```bash
# 1. 清除会话
curl -X DELETE "http://localhost:8000/api/chat/session/{SESSION_ID}?token={TOKEN}" | jq .
# Expected: {"ok":true,"deleted_messages":N,"deleted_memories":M}
curl -s "http://localhost:8000/api/chat/sessions?token={TOKEN}" | jq '.[] | select(.id=="{SESSION_ID}")'
# Expected: null (not returned)

# 2. 定时清理
docker exec hexo-agent-service python -c "
import asyncio; from app.core.cleanup import run_cleanup; asyncio.run(run_cleanup())
"
# 然后查 PG: SELECT COUNT(*) FROM agent_messages WHERE deleted_at IS NOT NULL;
# Expected: 0 (物理删除后)
```

### Final Checklist
- [x] All "Must Have" present
- [x] All "Must NOT Have" absent
- [x] All agent QA scenarios pass
- [x] Redis keys cleared on delete
- [x] PG soft delete working
- [x] Scheduler runs without error
- [x] Frontend clear button functional
