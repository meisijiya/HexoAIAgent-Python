# Phase 1: Agent 架构重构 - 详细实施计划

> **目标**: 重构为"对话 Agent 为中心"架构，简化 Orchestrator，实现工具调用机制和容错处理

**架构**: Orchestrator（简化路由）→ 对话 Agent（主控）→ 工具层（知识库/搜索/ReAct）

---

## Context

### 当前问题
1. Orchestrator 承担过多决策责任，意图识别优先级冲突
2. 知识库无匹配时需手动选择，用户体验差
3. ReAct Agent 不调用工具，直接编造答案
4. Agent 之间缺乏协作机制

### 目标架构
```
用户输入
    ↓
Orchestrator（简化：明确命令 + 默认路由）
    ↓
对话 Agent（主控：意图理解 + 工具选择 + 结果整合）
    ↓
工具层（知识库搜索 / 上网搜索 / ReAct 推理）
```

---

## 文件结构

```
agent-service/app/
├── core/
│   ├── orchestrator.py          # [重构] 简化路由
│   └── history_manager.py       # [修改] 添加压缩功能
├── agents/
│   ├── chat_agent.py            # [重构] 成为主控
│   ├── knowledge_agent.py       # [小改] 统一工具接口
│   ├── search_agent.py          # [修改] 结果整理
│   ├── react_agent.py           # [修改] 接收摘要上下文
│   └── tools.py                 # [保留] 现有工具定义
└── tools/                       # [新建] 工具封装目录
    ├── __init__.py
    ├── base.py                  # 工具基类
    ├── knowledge_tool.py        # 知识库工具
    ├── search_tool.py           # 搜索工具
    └── react_tool.py            # ReAct 工具
```

---

## Execution Strategy

```
Wave 1（基础框架 — 可并行）:
├── Task 1: 重构 Orchestrator [quick]
├── Task 2: 历史压缩器 [quick]
└── Task 3: 工具基类 [quick]

Wave 2（对话 Agent 重构 — 依赖 Wave 1）:
└── Task 4: 重构对话 Agent [unspecified-high]

Wave 3（工具集成 — 依赖 Wave 2）:
├── Task 5: 知识库工具封装 [quick]
├── Task 6: 搜索工具封装 [quick]
└── Task 7: ReAct 工具封装 [quick]

Wave 4（容错与提示 — 依赖 Wave 3）:
└── Task 8: 三级容错机制 + 工具调用提示 [unspecified-high]

Wave FINAL（测试验证）:
└── Task 9: 集成测试 [unspecified-high]
```

---

## TODOs

- [ ] 1. 重构 Orchestrator

  **What to do**:
  - 简化路由逻辑，只保留明确命令处理和默认路由
  - 明确命令：`/搜索 xxx` 路由到对话 Agent 并强制使用搜索工具
  - 明确命令：`/知识库 xxx` 路由到对话 Agent 并强制使用知识库工具
  - 默认：路由到对话 Agent，由对话 Agent 决定使用什么工具
  - 传递 session_id 给对话 Agent

  **Must NOT do**:
  - 不要删除命令处理逻辑
  - 不要在此处做复杂意图识别

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 简化重构，逻辑清晰

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 2, Task 3)
  - **Blocks**: Task 4
  - **Blocked By**: None

  **References**:
  - `agent-service/app/core/orchestrator.py`: 当前实现，理解现有结构
  - `agent-service/app/agents/chat_agent.py`: 需要了解对话 Agent 的接口

  **Acceptance Criteria**:
  - [ ] `/搜索 xxx` 命令正确路由到对话 Agent（force_tool="search_web"）
  - [ ] `/知识库 xxx` 命令正确路由到对话 Agent（force_tool="search_knowledge"）
  - [ ] 普通消息默认路由到对话 Agent
  - [ ] session_id 正确传递

---

- [ ] 2. 历史压缩器

  **What to do**:
  - 在 `history_manager.py` 中添加 `compress_for_tool` 方法
  - 提取最近 2 轮对话（4条消息）
  - 提取讨论主题（技术名词）
  - 构建摘要格式：对话上下文 + 当前问题
  - 单问题场景下不压缩（返回原问题）

  **Must NOT do**:
  - 不要删除现有历史管理功能
  - 不要过度压缩导致信息丢失

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 简单的字符串处理逻辑

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 1, Task 3)
  - **Blocks**: Task 4
  - **Blocked By**: None

  **References**:
  - `agent-service/app/core/history_manager.py`: 现有历史管理器
  - `agent-service/app/core/llm.py`: LLM 调用接口

  **Acceptance Criteria**:
  - [ ] 空历史时返回原问题
  - [ ] 有历史时返回摘要 + 当前问题
  - [ ] 摘要包含最近讨论主题
  - [ ] 不丢失最近记忆

---

- [ ] 3. 工具基类

  **What to do**:
  - 创建 `agent-service/app/tools/` 目录
  - 实现 `BaseTool` 基类
  - 定义统一接口：`name`, `description`, `execute()`
  - 实现工具注册机制

  **Must NOT do**:
  - 不要删除 `agents/tools.py`（保留兼容）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 简单的类设计

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 1, Task 2)
  - **Blocks**: Task 5, 6, 7
  - **Blocked By**: None

  **References**:
  - `agent-service/app/agents/tools.py`: 现有工具定义，参考接口设计

  **Acceptance Criteria**:
  - [ ] BaseTool 基类定义清晰
  - [ ] 统一的 execute 接口
  - [ ] 工具注册机制可用

---

- [ ] 4. 重构对话 Agent

  **What to do**:
  - 重写 `chat_agent.py` 成为主控 Agent
  - 实现系统提示词（工具描述 + 决策规则）
  - 实现工具选择逻辑（LLM 决定是否调用工具）
  - 实现 force_tool 参数（强制使用指定工具）
  - 实现结果整合逻辑
  - 集成三级容错机制

  **Must NOT do**:
  - 不要删除现有的对话功能
  - 不要修改其他 Agent 的接口

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 复杂的逻辑重构，需要理解整体架构

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (sequential)
  - **Blocks**: Task 5, 6, 7, 8
  - **Blocked By**: Task 1, 2, 3

  **References**:
  - `agent-service/app/agents/chat_agent.py`: 当前实现
  - `agent-service/app/core/orchestrator.py`: 理解调用方式
  - `agent-service/app/core/llm.py`: LLM 调用接口
  - `agent-service/app/core/history_manager.py`: 历史管理

  **Acceptance Criteria**:
  - [ ] 系统提示词包含工具描述和决策规则
  - [ ] LLM 可以决定调用哪个工具
  - [ ] force_tool 参数正常工作
  - [ ] 工具结果正确整合
  - [ ] 容错机制正常工作

---

- [ ] 5. 知识库工具封装

  **What to do**:
  - 创建 `tools/knowledge_tool.py`
  - 继承 BaseTool
  - 封装现有 `knowledge_agent.search_and_answer_with_info()`
  - 传递仅当前问题（不传递历史）
  - 返回格式化结果

  **Must NOT do**:
  - 不要修改 knowledge_agent 的内部逻辑

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 简单的封装

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Task 6, 7)
  - **Blocks**: Task 8
  - **Blocked By**: Task 4

  **References**:
  - `agent-service/app/agents/knowledge_agent.py`: 现有实现
  - `agent-service/app/tools/base.py`: 工具基类

  **Acceptance Criteria**:
  - [ ] 继承 BaseTool
  - [ ] 正确调用 knowledge_agent
  - [ ] 返回格式化结果

---

- [ ] 6. 搜索工具封装

  **What to do**:
  - 创建 `tools/search_tool.py`
  - 继承 BaseTool
  - 封装百度搜索 API
  - 实现结果整理（提取重要信息）
  - 传递仅当前问题

  **Must NOT do**:
  - 不要修改 search_agent 的内部逻辑

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 简单的封装

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Task 5, 7)
  - **Blocks**: Task 8
  - **Blocked By**: Task 4

  **References**:
  - `agent-service/app/agents/search_agent.py`: 现有实现

  **Acceptance Criteria**:
  - [ ] 继承 BaseTool
  - [ ] 正确调用百度搜索
  - [ ] 返回整理后的重要信息

---

- [ ] 7. ReAct 工具封装

  **What to do**:
  - 创建 `tools/react_tool.py`
  - 继承 BaseTool
  - 封装 react_agent.process()
  - 传递摘要上下文（对话摘要 + 当前问题）
  - 保持 ReAct 的 5 次循环限制

  **Must NOT do**:
  - 不要修改 react_agent 的内部逻辑

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 简单的封装

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Task 5, 6)
  - **Blocks**: Task 8
  - **Blocked By**: Task 4

  **References**:
  - `agent-service/app/agents/react_agent.py`: 现有实现
  - `agent-service/app/core/history_manager.py`: 历史压缩

  **Acceptance Criteria**:
  - [ ] 继承 BaseTool
  - [ ] 正确传递摘要上下文
  - [ ] 保持 5 次循环限制

---

- [ ] 8. 三级容错机制 + 工具调用提示

  **What to do**:
  - 在对话 Agent 中实现三级容错
  - 第1次失败 → 重试
  - 第2次失败 → 重试
  - 第3次失败 → fallback 到 LLM + 询问是否搜索
  - 实现工具调用提示消息

  **Must NOT do**:
  - 不要静默失败
  - 不要跳过重试直接 fallback

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 复杂的错误处理逻辑

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (sequential)
  - **Blocks**: Task 9
  - **Blocked By**: Task 5, 6, 7

  **References**:
  - `agent-service/app/agents/error_handler.py`: 现有错误处理

  **Acceptance Criteria**:
  - [ ] 重试 2 次后才 fallback
  - [ ] fallback 时提示用户
  - [ ] 询问是否搜索的选项正常工作
  - [ ] 工具调用提示正常显示

---

- [ ] 9. 集成测试

  **What to do**:
  - 测试 Orchestrator 路由
  - 测试对话 Agent 工具选择
  - 测试知识库搜索场景
  - 测试上网搜索场景
  - 测试 ReAct 推理场景
  - 测试容错 fallback 场景

  **Must NOT do**:
  - 不要跳过任何测试场景

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 复杂的集成测试

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave FINAL
  - **Blocks**: None
  - **Blocked By**: Task 8

  **References**:
  - `agent-service/test/`: 现有测试

  **Acceptance Criteria**:
  - [ ] 所有测试场景通过
  - [ ] 无明显 bug

---

## Final Verification Wave

- [ ] F1. **代码质量审查** — `unspecified-high`
  确认所有任务正确实现，代码无明显问题

- [ ] F2. **集成测试** — `unspecified-high`
  启动服务，测试各场景
