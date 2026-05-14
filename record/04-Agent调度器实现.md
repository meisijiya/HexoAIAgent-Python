# Agent 调度器实现

> 📅 日期：2024-05-14
> 🏷️ 标签：Orchestrator、意图识别、Agent 路由

---

## 📖 概述

本文记录 Agent 调度器（Orchestrator）的实现过程，包括意图识别、Agent 路由、多 Agent 协作等。

---

## 🎯 为什么需要调度器

### 问题场景

用户输入多种类型的问题：
- "你好" → 普通对话
- "Hexo 怎么安装" → 知识库问答
- "搜索最新的 AI 新闻" → 外部搜索

### 解决方案

```
用户输入
    ↓
Orchestrator（调度器）
    ↓
意图识别
    ↓
┌─────────┬─────────┬─────────┐
│ 对话    │ 知识库  │ 搜索    │
│ Agent   │ Agent   │ Agent   │
└─────────┴─────────┴─────────┘
```

---

## 🏗️ 调度器架构

### 核心组件

```python
# app/core/orchestrator.py
class Orchestrator:
    """Agent 调度器"""
    
    def __init__(self):
        self.agents = {
            "chat": ChatAgent(),
            "knowledge": KnowledgeAgent(),
            "search": SearchAgent(),
        }
    
    async def process(self, message: str, session_id: str, command: str = None):
        """处理用户消息"""
        
        # 1. 确定使用哪个 Agent
        agent_type = await self._determine_agent(message, command)
        
        # 2. 发送路由信息
        yield {"type": "routing", "agent": agent_type}
        
        # 3. 调用对应 Agent
        agent = self.agents[agent_type]
        async for chunk in agent.process(message, session_id):
            yield {"type": "content", "content": chunk}
        
        # 4. 发送完成信号
        yield {"type": "done", "agent": agent_type}
```

---

## 🧠 意图识别

### 方法一：关键词匹配（简单）

```python
async def _determine_agent_by_keyword(self, message: str, command: str = None):
    """基于关键词的意图识别"""
    
    # 明确命令
    if command:
        if command.startswith("/搜索"):
            return "search"
        elif command.startswith("/知识库"):
            return "knowledge"
    
    # 关键词匹配
    knowledge_keywords = ["怎么", "如何", "是什么", "为什么", "教程", "配置"]
    search_keywords = ["搜索", "查找", "最新", "新闻"]
    
    for keyword in knowledge_keywords:
        if keyword in message:
            return "knowledge"
    
    for keyword in search_keywords:
        if keyword in message:
            return "search"
    
    return "chat"
```

### 方法二：LLM 意图识别（推荐）

```python
INTENT_PROMPT = """你是一个意图分析助手。根据用户的消息，判断应该使用哪个 Agent。

Agent 类型：
- chat: 普通对话、闲聊、通用问题
- knowledge: 关于技术文档、教程、配置相关的问题
- search: 需要最新信息、实时数据、或者明确要求搜索

请只返回一个单词：chat、knowledge 或 search

用户消息：{message}

判断结果："""

async def _determine_agent_by_llm(self, message: str, command: str = None):
    """基于 LLM 的意图识别"""
    
    # 明确命令
    if command:
        if command.startswith("/搜索"):
            return "search"
        elif command.startswith("/知识库"):
            return "knowledge"
    
    # LLM 意图识别
    prompt = INTENT_PROMPT.format(message=message)
    messages = [{"role": "user", "content": prompt}]
    
    response = await llm_client.chat(messages, temperature=0.1, max_tokens=10)
    intent = response.strip().lower()
    
    if "knowledge" in intent:
        return "knowledge"
    elif "search" in intent:
        return "search"
    else:
        return "chat"
```

### 方法三：混合识别（最佳）

```python
async def _determine_agent(self, message: str, command: str = None):
    """混合意图识别"""
    
    # 1. 明确命令优先
    if command:
        if command.startswith("/搜索"):
            return "search"
        elif command.startswith("/知识库"):
            return "knowledge"
    
    # 2. 关键词快速判断
    quick_result = self._quick_classify(message)
    if quick_result:
        return quick_result
    
    # 3. LLM 精确判断
    return await self._determine_agent_by_llm(message)

def _quick_classify(self, message: str):
    """快速分类（关键词）"""
    search_keywords = ["搜索", "查找", "最新", "新闻", "今天", "现在"]
    
    for keyword in search_keywords:
        if keyword in message:
            return "search"
    
    return None  # 无法快速判断，交给 LLM
```

---

## 🔀 Agent 路由

### 路由表

| Agent | 职责 | 触发条件 |
|-------|------|----------|
| ChatAgent | 普通对话 | 默认 |
| KnowledgeAgent | 知识库问答 | 技术问题、教程问题 |
| SearchAgent | 外部搜索 | 搜索请求、实时信息 |

### 路由实现

```python
async def process(self, message: str, session_id: str, command: str = None):
    """处理用户消息"""
    
    # 1. 意图识别
    agent_type = await self._determine_agent(message, command)
    agent_name = AGENT_NAMES.get(agent_type, "未知 Agent")
    
    # 2. 发送路由信息（显示调用的 Agent）
    yield {
        "type": "routing",
        "agent": agent_type,
        "agent_name": agent_name,
        "message": f"🤖 正在调用 {agent_name}..."
    }
    
    # 3. 调用对应 Agent
    agent = self.agents[agent_type]
    async for msg in agent.process(message, session_id):
        yield msg
    
    # 4. 发送完成信号
    yield {"type": "done", "agent": agent_type}
```

---

## 🤖 Agent 实现

### ChatAgent（对话 Agent）

```python
# app/agents/chat_agent.py
class ChatAgent:
    """对话 Agent"""
    
    async def process(self, message: str, session_id: str):
        # 1. 获取历史上下文
        context = await get_session_context(session_id)
        
        # 2. 构建消息列表
        messages = self._build_messages(message, context)
        
        # 3. 调用 LLM
        full_response = ""
        async for chunk in llm_client.chat_stream(messages):
            full_response += chunk
            yield {"type": "content", "content": chunk}
        
        # 4. 保存到记忆
        await add_message_to_context(session_id, "user", message)
        await add_message_to_context(session_id, "assistant", full_response)
```

### KnowledgeAgent（知识库 Agent）

```python
# app/agents/knowledge_agent.py
class KnowledgeAgent:
    """知识库 Agent"""
    
    async def process(self, message: str, session_id: str):
        # 1. 检索相关文档
        search_results = await retriever.search(db, message, top_k=3)
        
        # 2. 发送来源信息
        if search_results:
            yield {
                "type": "knowledge_sources",
                "message": f"📚 找到 {len(search_results)} 条相关文档",
                "articles": self._format_sources(search_results)
            }
        
        # 3. 构建上下文
        context = self._build_context(search_results)
        
        # 4. 生成回答
        messages = [
            {"role": "system", "content": KNOWLEDGE_PROMPT},
            {"role": "user", "content": f"参考资料：\n{context}\n\n用户问题：{message}"}
        ]
        
        async for chunk in llm_client.chat_stream(messages):
            yield {"type": "content", "content": chunk}
```

### SearchAgent（搜索 Agent）

```python
# app/agents/search_agent.py
class SearchAgent:
    """搜索 Agent"""
    
    async def process(self, message: str, session_id: str):
        # 1. 执行搜索
        search_results = await self._search(message)
        
        # 2. 构建上下文
        context = self._build_context(search_results)
        
        # 3. 生成回答
        messages = [
            {"role": "system", "content": SEARCH_PROMPT},
            {"role": "user", "content": f"搜索结果：\n{context}\n\n用户问题：{message}"}
        ]
        
        async for chunk in llm_client.chat_stream(messages):
            yield {"type": "content", "content": chunk}
```

---

## 📡 SSE 流式输出

### 事件类型

| 事件 | 说明 | 数据格式 |
|------|------|----------|
| routing | 路由信息 | `{"type": "routing", "agent": "knowledge"}` |
| sources | 知识库来源 | `{"type": "knowledge_sources", "articles": [...]}` |
| content | 回复内容 | `{"content": "回答内容"}` |
| done | 完成信号 | `{"type": "done", "agent": "knowledge"}` |

### 前端处理

```javascript
// 处理 SSE 事件
const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    const text = decoder.decode(value);
    const lines = text.split('\n');
    
    for (const line of lines) {
        if (line.startsWith('event: ')) {
            const eventType = line.slice(7).trim();
            const nextLine = lines[lines.indexOf(line) + 1];
            
            if (nextLine && nextLine.startsWith('data: ')) {
                const data = JSON.parse(nextLine.slice(6));
                
                if (eventType === 'routing') {
                    addAgentInfo(data.agent_name, data.message);
                } else if (eventType === 'sources') {
                    addKnowledgeSources(data.articles);
                }
            }
        } else if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6));
            if (data.content) {
                appendContent(data.content);
            }
        }
    }
}
```

---

## 🧪 测试效果

### 测试用例

| 输入 | 预期 Agent | 实际 Agent | 结果 |
|------|------------|------------|------|
| "你好" | chat | chat | ✅ |
| "Hexo 怎么安装" | knowledge | knowledge | ✅ |
| "搜索最新新闻" | search | search | ✅ |
| "Redis 分布式锁" | knowledge | knowledge | ✅ |

### 测试命令

```bash
# 普通对话
curl -X POST http://localhost:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "token": "xxx"}'

# 知识库问答
curl -X POST http://localhost:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hexo 怎么安装", "token": "xxx"}'

# 搜索
curl -X POST http://localhost:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "/搜索 最新新闻", "token": "xxx"}'
```

---

## 🎯 优化方向

### 1. 意图识别优化

- 训练分类模型
- 多标签分类
- 置信度阈值

### 2. 路由策略优化

- 动态路由
- 多 Agent 协作
- 回退机制

### 3. 性能优化

- 并行调用
- 缓存机制
- 预测性加载

---

## 📝 总结

### 关键点

1. **Orchestrator 模式**：统一调度，解耦 Agent
2. **意图识别**：关键词 + LLM 混合方案
3. **SSE 流式输出**：实时反馈，提升体验
4. **Agent 协作**：可扩展的架构

### 设计亮点

1. **模块化**：每个 Agent 独立，易于扩展
2. **可配置**：支持多种意图识别方式
3. **容错性**：识别失败时默认对话 Agent
4. **可观察**：显示调用的 Agent 类型

### 后续优化

1. **ReAct 模式**：支持工具调用
2. **多轮对话**：上下文记忆优化
3. **性能优化**：缓存、并行

---

## 📚 参考资源

- [ReAct 论文](https://arxiv.org/abs/2210.03629)
- [LangChain Agent](https://python.langchain.com/docs/modules/agents/)
- [FastAPI SSE](https://fastapi.tiangolo.com/advanced/custom-response/)

---

**上一篇：[RAG 知识库实现](./03-RAG知识库实现.md)** ← → **下一篇：[RAG 检索优化](./05-RAG检索优化.md)** →
