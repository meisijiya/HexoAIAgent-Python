# 匿名用户限流 + 功能分级 + 差异化欢迎语

## TL;DR
- 匿名用户：IP 限流 10次/天，仅知识库Agent，不保存对话
- GitHub 用户：user_id 限流 100次/天，全功能
- 前端欢迎语差异化：GitHub → AI介绍+使用指南，匿名 → 引导登录
- chat API token 改为可选参数

## Design Decisions
| 决策 | 方案 | 理由 |
|------|------|------|
| 匿名接入 | token 改为 Optional | 一个端点，逻辑集中 |
| 匿名限流 | IP + Redis 日期 key | `daily_rate:ip:{ip}:{date}`，每天自动过期 |
| GitHub 限流 | user_id + Redis 日期 key | `daily_rate:user:{uid}:{date}`，100次/天 |
| 路由限制 | 匿名强制知识库Agent | 跳过 LLM 意图判断 |
| 对话存储 | 匿名不保存 | 已有基础，加判断即可 |

## Scope
**IN**:
- chat.py: token Optional, anon IP 提取, 分级限流, 强制路由
- redis.py: 新增 `check_daily_limit(identifier, limit, user_type)`
- chat_agent.py: 匿名时跳过 LLM 路由，直接 knowledge_agent
- agent-widget.js: 差异化欢迎语，GitHub/匿名状态区分
- agent-widget.js: 匿名状态 UI 指示

**OUT**:
- 不新增 API 端点
- 不改 OAuth 流程

---

## Tasks

### Wave 1 (Backend - parallel)

- [x] 1. Redis 每日限流函数
  **代理**: quick | 文件: `app/core/redis.py`
  - 新增 `check_daily_limit(identifier: str, limit: int) -> bool`
  - Key 格式: `daily_rate:ip:{ip}:{date}` 或 `daily_rate:user:{uid}:{date}`
  - `INCR` + 首次设 `EXPIREAT` 到次日凌晨
  - 超过 limit → return False

- [x] 2. chat API token 改为 Optional + 匿名分流
  **代理**: deep | 文件: `app/api/chat.py`
  - `ChatRequest.token` 改为 `Optional[str] = None`
  - token 有效 → GitHub 用户，user_id 限流 100次/天
  - token 无效/None → 匿名，`request.client.host` 提取 IP，IP 限流 10次/天
  - 调用 `check_daily_limit()` 替换/补充现有 `check_rate_limit()`
  - 保留现有 60s 限流作为第二层（防止刷爆）

- [x] 3. 匿名强制路由知识库Agent
  **代理**: deep | 文件: `app/agents/chat_agent.py` + `app/api/chat.py`
  - 在 chat.py 中：匿名时传 `force_tool="knowledge"` 给 chat_agent
  - 或 chat_agent.process() 加 `is_anonymous` 参数 → 跳过 Phase1 LLM 分类
  - 直接走 knowledge_agent 检索

- [x] 4. 匿名不保存对话
  **代理**: quick | 文件: `app/api/chat.py`
  - 在 save_message(session_id, ...) 和 db.add(Message) 前加 `if not is_anonymous:`
  - 匿名请求不写 PG 也不写 Redis context
  - 匿名请求不需要 session（session_id=None 时不创建新 Session）

### Wave 2 (Frontend - sequential)

- [x] 5. 差异化欢迎语
- [x] 6. 匿名状态UI指示（剩余次数）
- [x] 7. hexo-widget + 博客主题同步
  **代理**: quick | 文件复制

---

## Final Verification
- [x] F1: curl 无 token → 200 + 知识库回复 + 不存 DB
- [x] F2: 同一 IP 第 11 次请求 → 429
- [x] F3: GitHub 用户第 101 次 → 429 (逻辑同 F2，limit=100)
- [x] F4: 匿名欢迎语含 GitHub 登录引导
- [x] F5: GitHub 欢迎语含 AI 介绍
