# 对话 Agent 优化分析

> 📅 日期：2024-05-14
> 🏷️ 标签：Agent 优化、架构设计、最佳实践

---

## 📖 概述

本文基于参考博客《对话 Agent 的核心流程解析》，分析当前实现的优化点，并提出改进方案。

---

## 🏗️ 参考架构 vs 当前实现

### 参考架构核心组件

```
用户输入
    ↓
Lambda Node (InputToRag)
    ↓
Retriever (向量召回)
    ↓
Lambda Node (InputToChat)
    ↓
ChatTemplate (Prompt 构建)
    ↓
ReAct 模式 (思考-行动-观察)
    ↓
最终答案
```

### 当前实现对比

| 组件 | 参考架构 | 当前实现 | 状态 |
|------|----------|----------|------|
| **RAG 召回** | Retriever + Milvus | Retriever + pgvector | ✅ 已实现 |
| **Prompt 构建** | ChatTemplate (结构化) | 简单字符串拼接 | ⚠️ 需优化 |
| **ReAct 模式** | 思考-行动-观察循环 | ReActAgent | ✅ 已实现 |
| **Lambda Node** | 数据流转转换器 | 无 | ❌ 未实现 |
| **Tool 定义** | 带描述的函数 | ToolCollection | ✅ 已实现 |
| **对话历史** | 带入 Prompt | Redis 存储 | ⚠️ 需优化 |

---

## 🎯 优化点分析

### 1️⃣ Prompt 构建优化

**当前问题**：
- Prompt 只是简单字符串拼接
- 没有结构化的占位符设计
- 对话历史没有融入 Prompt

**参考方案**：
```go
// ChatTemplate 设计
type ChatTemplate struct {
    SystemPrompt string
    RAGContext   string  // RAG 召回内容
    History      string  // 对话历史
    UserInput    string  // 用户输入
}

// 占位符设计
template := `
{{.SystemPrompt}}

## 参考资料
{{.RAGContext}}

## 对话历史
{{.History}}

## 用户问题
{{.UserInput}}

请基于以上信息回答用户问题。
`
```

**优化方案**：
```python
class PromptBuilder:
    """结构化 Prompt 构建器"""
    
    def build(
        self,
        system_prompt: str,
        rag_context: str = "",
        history: str = "",
        user_input: str = ""
    ) -> str:
        """构建结构化 Prompt"""
        
        parts = [system_prompt]
        
        if rag_context:
            parts.append(f"\n## 参考资料\n{rag_context}")
        
        if history:
            parts.append(f"\n## 对话历史\n{history}")
        
        parts.append(f"\n## 用户问题\n{user_input}")
        
        return "\n".join(parts)
```

---

### 2️⃣ Lambda Node 实现

**当前问题**：
- 数据流转没有统一处理
- 输入输出格式不一致

**参考方案**：
```go
// InputToRag: 用户输入 → RAG 查询
type InputToRag struct{}

func (n *InputToRag) Process(input map[string]interface{}) map[string]interface{} {
    userMessage := input["message"].(string)
    // 提取关键词，生成 RAG 查询
    ragQuery := extractKeywords(userMessage)
    input["rag_query"] = ragQuery
    return input
}

// InputToChat: 用户输入 + 历史 → Chat 输入
type InputToChat struct{}

func (n *InputToChat) Process(input map[string]interface{}) map[string]interface{} {
    userMessage := input["message"].(string)
    history := input["history"].(string)
    ragResults := input["documents"].(string)
    // 构建 Chat 输入
    input["chat_input"] = buildChatInput(userMessage, history, ragResults)
    return input
}
```

**优化方案**：
```python
class LambdaNode:
    """数据流转转换器"""
    
    def __init__(self, name: str):
        self.name = name
    
    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理数据"""
        raise NotImplementedError


class InputToRagNode(LambdaNode):
    """用户输入 → RAG 查询"""
    
    def __init__(self):
        super().__init__("InputToRag")
    
    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        user_message = data.get("message", "")
        
        # 提取关键词
        keywords = self._extract_keywords(user_message)
        
        # 生成 RAG 查询
        data["rag_query"] = " ".join(keywords)
        
        return data
    
    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        # 简单实现：分词后过滤停用词
        words = jieba.cut(text)
        stopwords = {"的", "了", "是", "在", "有", "和", "就", "不", "人", "都"}
        return [w for w in words if w not in stopwords and len(w) > 1]


class InputToChatNode(LambdaNode):
    """用户输入 + 历史 + RAG → Chat 输入"""
    
    def __init__(self):
        super().__init__("InputToChat")
    
    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        user_message = data.get("message", "")
        history = data.get("history", "")
        rag_results = data.get("documents", "")
        
        # 构建 Chat 输入
        data["chat_input"] = self._build_chat_input(
            user_message, history, rag_results
        )
        
        return data
    
    def _build_chat_input(
        self,
        user_message: str,
        history: str,
        rag_results: str
    ) -> str:
        """构建 Chat 输入"""
        
        parts = []
        
        if rag_results:
            parts.append(f"参考资料：\n{rag_results}")
        
        if history:
            parts.append(f"对话历史：\n{history}")
        
        parts.append(f"用户问题：{user_message}")
        
        return "\n\n".join(parts)
```

---

### 3️⃣ 对话历史优化

**当前问题**：
- 对话历史只是简单存储
- 没有摘要和压缩
- Token 消耗大

**优化方案**：
```python
class HistoryManager:
    """对话历史管理器"""
    
    async def get_history(
        self,
        session_id: str,
        max_messages: int = 10,
        max_tokens: int = 2000
    ) -> str:
        """
        获取对话历史（带压缩）
        
        Args:
            session_id: 会话 ID
            max_messages: 最大消息数
            max_tokens: 最大 Token 数
        
        Returns:
            str: 格式化的对话历史
        """
        
        # 获取原始消息
        messages = await get_session_context(session_id, max_messages)
        
        if not messages:
            return ""
        
        # 计算 Token 数
        total_tokens = sum(len(m["content"]) for m in messages)
        
        # 如果超过限制，进行压缩
        if total_tokens > max_tokens:
            messages = await self._compress_history(messages, max_tokens)
        
        # 格式化
        formatted = []
        for msg in messages:
            role = "用户" if msg["role"] == "user" else "助手"
            formatted.append(f"{role}: {msg['content'][:100]}...")
        
        return "\n".join(formatted)
    
    async def _compress_history(
        self,
        messages: List[Dict],
        max_tokens: int
    ) -> List[Dict]:
        """压缩对话历史"""
        
        # 策略 1: 只保留最近的消息
        if len(messages) > 5:
            messages = messages[-5:]
        
        # 策略 2: 截断长消息
        compressed = []
        for msg in messages:
            if len(msg["content"]) > 200:
                msg = msg.copy()
                msg["content"] = msg["content"][:200] + "..."
            compressed.append(msg)
        
        return compressed
```

---

### 4️⃣ RAG 召回优化

**当前问题**：
- 只有向量检索
- 没有查询改写
- 没有多路召回

**优化方案**：
```python
class EnhancedRetriever:
    """增强版检索器"""
    
    async def search(
        self,
        query: str,
        session_id: str = None,
        top_k: int = 5
    ) -> List[SearchResult]:
        """
        增强版搜索
        
        优化点：
        1. 查询改写
        2. 多路召回
        3. 结果融合
        """
        
        # 1. 查询改写
        rewritten_queries = await self._rewrite_query(query)
        
        # 2. 多路召回
        all_results = []
        for q in rewritten_queries:
            results = await self._vector_search(q, top_k)
            all_results.extend(results)
        
        # 3. 结果去重和排序
        unique_results = self._deduplicate(all_results)
        
        # 4. 返回 Top K
        return unique_results[:top_k]
    
    async def _rewrite_query(self, query: str) -> List[str]:
        """查询改写"""
        
        # 使用 LLM 改写查询
        prompt = f"""
请将以下查询改写为 2-3 个不同的搜索查询：

原始查询：{query}

要求：
1. 保持原意
2. 使用不同表达
3. 包含更多关键词

改写后的查询（每行一个）：
"""
        
        response = await llm_client.chat([{"role": "user", "content": prompt}])
        
        queries = [query] + [
            line.strip() for line in response.split("\n")
            if line.strip() and len(line.strip()) > 3
        ]
        
        return queries[:3]
    
    def _deduplicate(self, results: List[SearchResult]) -> List[SearchResult]:
        """结果去重"""
        
        seen = set()
        unique = []
        
        for r in results:
            if r.id not in seen:
                seen.add(r.id)
                unique.append(r)
        
        return sorted(unique, key=lambda x: x.score, reverse=True)
```

---

### 5️⃣ ReAct 循环优化

**当前问题**：
- 工具选择不够智能
- 循环终止条件简单
- 没有错误恢复

**优化方案**：
```python
class EnhancedReActAgent:
    """增强版 ReAct Agent"""
    
    def __init__(self):
        self.max_iterations = 5
        self.tool_selector = ToolSelector()
    
    async def process(self, query: str, session_id: str):
        """处理查询"""
        
        # 1. 获取对话历史
        history = await history_manager.get_history(session_id)
        
        # 2. RAG 召回
        rag_results = await retriever.search(query, session_id)
        
        # 3. 构建上下文
        context = self._build_context(query, history, rag_results)
        
        # 4. ReAct 循环
        messages = [{"role": "user", "content": context}]
        
        for i in range(self.max_iterations):
            # 调用 LLM
            response = await llm_client.chat(messages)
            
            # 解析响应
            thought, action, action_input, final_answer = self._parse(response)
            
            # 如果有最终答案
            if final_answer:
                yield {"type": "content", "content": final_answer}
                return
            
            # 如果需要调用工具
            if action:
                # 智能工具选择
                selected_tool = self.tool_selector.select(action, query)
                
                # 执行工具
                result = await tool_collection.call(selected_tool, action_input)
                
                # 添加到消息
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"Observation: {result}"})
        
        # 达到最大次数
        yield {"type": "content", "content": "抱歉，无法在有限步骤内回答。"}
    
    def _build_context(
        self,
        query: str,
        history: str,
        rag_results: List[SearchResult]
    ) -> str:
        """构建上下文"""
        
        parts = []
        
        if rag_results:
            rag_text = "\n".join([f"- {r.content[:100]}..." for r in rag_results])
            parts.append(f"参考资料：\n{rag_text}")
        
        if history:
            parts.append(f"对话历史：\n{history}")
        
        parts.append(f"用户问题：{query}")
        
        return "\n\n".join(parts)


class ToolSelector:
    """智能工具选择器"""
    
    def select(self, action: str, query: str) -> str:
        """选择最合适的工具"""
        
        # 关键词匹配
        if "搜索" in action or "查找" in action:
            return "search_knowledge"
        elif "列表" in action or "列出" in action:
            return "list_articles"
        elif "详情" in action or "获取" in action:
            return "get_article"
        else:
            return "search_knowledge"  # 默认
```

---

## 📊 优化优先级

| 优化项 | 优先级 | 难度 | 预期效果 |
|--------|--------|------|----------|
| **Prompt 构建优化** | ⭐⭐⭐⭐⭐ | ⭐⭐ | 提升回答质量 |
| **对话历史优化** | ⭐⭐⭐⭐ | ⭐⭐ | 减少 Token 消耗 |
| **Lambda Node 实现** | ⭐⭐⭐ | ⭐⭐⭐ | 代码更清晰 |
| **RAG 召回优化** | ⭐⭐⭐ | ⭐⭐⭐ | 提升检索准确率 |
| **ReAct 循环优化** | ⭐⭐ | ⭐⭐⭐⭐ | 提升工具调用准确率 |

---

## 🎯 推荐优化顺序

### 阶段一：Prompt 构建优化（1-2 天）

```python
# 实现 PromptBuilder
prompt_builder = PromptBuilder()

# 构建结构化 Prompt
prompt = prompt_builder.build(
    system_prompt=KNOWLEDGE_PROMPT,
    rag_context=rag_context,
    history=history,
    user_input=query
)
```

### 阶段二：对话历史优化（1 天）

```python
# 实现 HistoryManager
history_manager = HistoryManager()

# 获取压缩后的历史
history = await history_manager.get_history(
    session_id,
    max_messages=10,
    max_tokens=2000
)
```

### 阶段三：Lambda Node 实现（2 天）

```python
# 实现数据流转节点
input_to_rag = InputToRagNode()
input_to_chat = InputToChatNode()

# 使用
data = {"message": query}
data = input_to_rag.process(data)
data["documents"] = await retriever.search(data["rag_query"])
data = input_to_chat.process(data)
```

---

## 📝 总结

### 当前优势

1. ✅ 基础 RAG 召回已实现
2. ✅ ReAct 模式已实现
3. ✅ 工具调用机制已实现
4. ✅ 动态阈值和 Top K

### 需要优化

1. ⚠️ Prompt 构建需要结构化
2. ⚠️ 对话历史需要压缩
3. ⚠️ 数据流转需要 Lambda Node
4. ⚠️ RAG 召回可以更智能

### 核心思想

参考博客的总结非常到位：

> Agent 能力的三角支柱：
> 1. **RAG 召回**：赋予外部知识记忆能力
> 2. **动态 Prompt**：让大模型学习外部知识，并带有记忆
> 3. **ReAct 模式**：实现复杂任务拆解与工具调用

---

## 📚 参考资源

- [对话 Agent 的核心流程解析](参考博客链接)
- [ReAct 论文](https://arxiv.org/abs/2210.03629)
- [LangChain Agent](https://python.langchain.com/docs/modules/agents/)

---

**上一篇：[ReAct 架构优化](./07-ReAct架构优化.md)** ←
