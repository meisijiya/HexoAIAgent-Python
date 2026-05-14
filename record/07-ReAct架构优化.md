# ReAct 架构优化

> 📅 日期：2024-05-14
> 🏷️ 标签：ReAct、工具调用、推理循环、Agent 架构

---

## 📖 概述

本文记录 ReAct（Reasoning + Acting）架构的优化过程，包括工具调用机制、思考-行动-观察循环等。

---

## 🎯 什么是 ReAct

### 核心思想

ReAct = **Re**asoning（推理）+ **Act**ing（行动）

```
思考 → 行动 → 观察 → 再思考 → ...
```

### 执行流程

```
用户问题
    ↓
思考：分析问题，制定计划
    ↓
行动：调用工具（搜索、查询等）
    ↓
观察：查看工具返回结果
    ↓
判断：是否需要继续？
    ├─ 是 → 回到"思考"
    └─ 否 → 生成最终回答
```

### 古法 vs 现代

| 特性 | 古法 ReAct | 现代 ReAct |
|------|------------|------------|
| 工具定义 | 字符串描述 | JSON Schema |
| 调用格式 | Thought/Action/Pause | Function Call |
| 解析方式 | 字符串解析 | 结构化解析 |
| 错误处理 | 复杂 | 简单 |
| Token 消耗 | 高 | 低 |

---

## 🏗️ 架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    ReAct Agent                               │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  思考模块   │  │  行动模块   │  │  观察模块   │         │
│  │ (Reasoning) │  │  (Acting)   │  │ (Observing) │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│         ↑                ↓                ↑                 │
│         └────────────────┴────────────────┘                 │
│                        循环                                  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    工具集合                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ 知识库搜索  │  │ Web 搜索    │  │ 数据库查询  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

### 核心组件

```python
class ReActAgent:
    """ReAct Agent"""
    
    def __init__(self):
        self.llm = LLMClient()
        self.tools = ToolCollection()
        self.max_iterations = 5  # 最大循环次数
    
    async def process(self, query: str) -> str:
        """
        处理用户查询
        
        Args:
            query: 用户查询
        
        Returns:
            str: 最终回答
        """
        
        # 初始化
        messages = [
            {"role": "system", "content": REACT_PROMPT},
            {"role": "user", "content": query}
        ]
        
        # 循环执行
        for i in range(self.max_iterations):
            # 1. 思考：让 LLM 决定下一步
            response = await self.llm.chat(messages)
            
            # 2. 解析响应
            thought, action, action_input = self._parse_response(response)
            
            # 3. 判断是否结束
            if action == "FINISH":
                return thought
            
            # 4. 行动：调用工具
            observation = await self.tools.call(action, action_input)
            
            # 5. 观察：将结果添加到消息
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": f"Observation: {observation}"})
        
        # 达到最大循环次数
        return "抱歉，我无法在有限步骤内回答这个问题。"
```

---

## 🔧 工具定义

### 工具 Schema

```python
# 工具定义
tools = [
    {
        "name": "search_knowledge",
        "description": "搜索知识库中的文档",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_web",
        "description": "搜索互联网获取最新信息",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_article",
        "description": "获取文章详细内容",
        "parameters": {
            "type": "object",
            "properties": {
                "article_id": {
                    "type": "string",
                    "description": "文章 ID"
                }
            },
            "required": ["article_id"]
        }
    }
]
```

### 工具实现

```python
class ToolCollection:
    """工具集合"""
    
    def __init__(self):
        self.tools = {
            "search_knowledge": self._search_knowledge,
            "search_web": self._search_web,
            "get_article": self._get_article,
        }
    
    async def call(self, tool_name: str, tool_input: Dict) -> str:
        """
        调用工具
        """
        
        if tool_name not in self.tools:
            return f"错误：工具 {tool_name} 不存在"
        
        try:
            return await self.tools[tool_name](tool_input)
        except Exception as e:
            return f"工具调用失败：{str(e)}"
    
    async def _search_knowledge(self, params: Dict) -> str:
        """搜索知识库"""
        query = params.get("query", "")
        results = await retriever.search(query, top_k=3)
        
        if not results:
            return "知识库中没有找到相关文档"
        
        # 格式化结果
        formatted = []
        for i, r in enumerate(results, 1):
            formatted.append(f"[{i}] {r.content[:100]}...")
        
        return "\n".join(formatted)
    
    async def _search_web(self, params: Dict) -> str:
        """搜索互联网"""
        query = params.get("query", "")
        results = await search_agent.search(query)
        
        if not results:
            return "搜索没有找到相关结果"
        
        # 格式化结果
        formatted = []
        for i, r in enumerate(results, 1):
            formatted.append(f"[{i}] {r['title']}: {r['snippet']}")
        
        return "\n".join(formatted)
    
    async def _get_article(self, params: Dict) -> str:
        """获取文章"""
        article_id = params.get("article_id", "")
        
        # 查询数据库
        article = await db.get(Article, article_id)
        
        if not article:
            return f"文章 {article_id} 不存在"
        
        return f"标题：{article.title}\n内容：{article.content[:500]}..."
```

---

## 🧠 Prompt 设计

### ReAct Prompt

```python
REACT_PROMPT = """你是一个智能助手，可以使用以下工具来回答问题：

工具列表：
{tools_description}

请使用以下格式回答问题：

Thought: 我需要思考一下这个问题...
Action: 工具名称
Action Input: 工具参数（JSON 格式）
Observation: 工具返回的结果
...（可以重复多次）
Thought: 我现在知道答案了
Final Answer: 最终答案

规则：
1. 每次只能调用一个工具
2. 工具参数必须是有效的 JSON
3. 如果不需要工具，可以直接给出答案
4. 如果无法回答，诚实地说不知道

用户问题：{query}

请开始回答："""
```

### 工具描述生成

```python
def generate_tools_description(tools: List[Dict]) -> str:
    """生成工具描述"""
    
    descriptions = []
    for tool in tools:
        desc = f"- {tool['name']}: {tool['description']}\n"
        desc += f"  参数: {json.dumps(tool['parameters'], ensure_ascii=False)}"
        descriptions.append(desc)
    
    return "\n".join(descriptions)
```

---

## 🔄 Function Call 实现

### 现代 ReAct（使用 Function Call）

```python
class ModernReActAgent:
    """现代 ReAct Agent（使用 Function Call）"""
    
    async def process(self, query: str) -> str:
        """
        处理用户查询
        """
        
        messages = [
            {"role": "system", "content": "你是一个智能助手，可以使用工具来回答问题。"},
            {"role": "user", "content": query}
        ]
        
        for i in range(self.max_iterations):
            # 调用 LLM（带工具定义）
            response = await self.llm.chat_with_tools(
                messages=messages,
                tools=tools
            )
            
            # 检查是否有工具调用
            if response.tool_calls:
                # 处理工具调用
                for tool_call in response.tool_calls:
                    # 执行工具
                    result = await self.tools.call(
                        tool_call.function.name,
                        json.loads(tool_call.function.arguments)
                    )
                    
                    # 添加工具结果到消息
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result
                    })
            else:
                # 没有工具调用，返回最终答案
                return response.content
        
        return "抱歉，我无法在有限步骤内回答这个问题。"
```

### DeepSeek Function Call

```python
class DeepSeekLLM:
    """DeepSeek LLM（支持 Function Call）"""
    
    async def chat_with_tools(self, messages: List[Dict], tools: List[Dict]) -> Dict:
        """
        调用 LLM（带工具）
        """
        
        response = await self.client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        
        return response.choices[0].message
```

---

## 📊 执行流程示例

### 示例 1：简单问题

```
用户：什么是 Redis？

思考：这是一个基本概念问题，我可以直接回答。
Final Answer: Redis 是一个开源的内存数据结构存储系统...
```

### 示例 2：需要工具

```
用户：Redis 分布式锁怎么实现？

思考：这是一个技术问题，我需要搜索知识库。
Action: search_knowledge
Action Input: {"query": "Redis 分布式锁实现"}
Observation: [1] Redis 分布式锁的核心原理是利用 SETNX 命令...

思考：我找到了相关信息，现在可以回答了。
Final Answer: Redis 分布式锁的实现方式是...
```

### 示例 3：多步推理

```
用户：对比 Redis 和 Memcached

思考：我需要分别了解 Redis 和 Memcached。
Action: search_knowledge
Action Input: {"query": "Redis 特点"}
Observation: Redis 支持多种数据结构...

Action: search_knowledge
Action Input: {"query": "Memcached 特点"}
Observation: Memcached 是简单的键值存储...

思考：我现在可以对比两者了。
Final Answer: Redis 和 Memcached 的主要区别...
```

---

## 🧪 测试用例

### 测试场景

```python
test_cases = [
    # 简单问题（不需要工具）
    {
        "query": "什么是 Git？",
        "expected": "直接回答",
        "tools_used": []
    },
    
    # 需要知识库
    {
        "query": "Hexo 怎么部署到 GitHub？",
        "expected": "知识库回答",
        "tools_used": ["search_knowledge"]
    },
    
    # 需要搜索
    {
        "query": "2024 年最新的 AI 技术",
        "expected": "搜索回答",
        "tools_used": ["search_web"]
    },
    
    # 多步推理
    {
        "query": "对比 Spring Boot 和 Django",
        "expected": "多步查询",
        "tools_used": ["search_knowledge", "search_knowledge"]
    }
]
```

### 测试代码

```python
async def test_react_agent():
    """测试 ReAct Agent"""
    
    agent = ReActAgent()
    
    for case in test_cases:
        print(f"测试: {case['query']}")
        
        result = await agent.process(case["query"])
        
        # 验证结果
        assert result is not None
        print(f"结果: {result[:50]}...")
        print()
```

---

## 📈 性能优化

### 1. 并行工具调用

```python
async def process_with_parallel_tools(self, query: str) -> str:
    """并行调用工具"""
    
    # 分析需要哪些工具
    tools_needed = await self._analyze_tools_needed(query)
    
    # 并行调用
    tasks = [
        self.tools.call(tool["name"], tool["input"])
        for tool in tools_needed
    ]
    
    results = await asyncio.gather(*tasks)
    
    # 综合结果
    return await self._synthesize_results(query, results)
```

### 2. 缓存机制

```python
class CachedTool:
    """带缓存的工具"""
    
    def __init__(self, tool, cache_ttl=300):
        self.tool = tool
        self.cache = {}
        self.cache_ttl = cache_ttl
    
    async def call(self, params: Dict) -> str:
        # 生成缓存 key
        cache_key = f"{self.tool.name}:{json.dumps(params)}"
        
        # 检查缓存
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            if time.time() - cached["time"] < self.cache_ttl:
                return cached["result"]
        
        # 调用工具
        result = await self.tool.call(params)
        
        # 更新缓存
        self.cache[cache_key] = {
            "result": result,
            "time": time.time()
        }
        
        return result
```

### 3. 提前终止

```python
async def process_with_early_stop(self, query: str) -> str:
    """提前终止"""
    
    messages = [{"role": "user", "content": query}]
    
    for i in range(self.max_iterations):
        response = await self.llm.chat(messages)
        
        # 检查是否有足够信息回答
        if self._has_enough_info(response):
            return self._extract_answer(response)
        
        # 继续工具调用
        # ...
```

---

## 🎯 最佳实践

### 1. 工具设计原则

- **单一职责**：每个工具做一件事
- **清晰描述**：工具描述要准确
- **参数验证**：验证输入参数
- **错误处理**：优雅处理异常

### 2. Prompt 设计原则

- **明确格式**：指定输出格式
- **提供示例**：给出 few-shot 示例
- **约束行为**：限制循环次数
- **错误引导**：引导正确使用工具

### 3. 循环控制

- **最大次数**：限制循环次数
- **超时机制**：设置超时时间
- **提前终止**：检测到答案时终止
- **错误回退**：出错时回退到简单回答

---

## 📝 总结

### 关键点

1. **ReAct 模式**：思考-行动-观察循环
2. **工具调用**：统一的工具定义和调用
3. **Function Call**：现代的结构化调用方式
4. **循环控制**：防止无限循环

### 架构优势

1. **可扩展**：易于添加新工具
2. **可解释**：思考过程透明
3. **灵活**：支持多步推理
4. **可靠**：有循环控制和错误处理

### 后续优化

1. **并行调用**：提高效率
2. **缓存机制**：减少重复调用
3. **智能路由**：根据问题类型选择工具
4. **学习优化**：从历史中学习最优策略

---

## 📚 参考资源

- [ReAct 论文](https://arxiv.org/abs/2210.03629)
- [LangChain Agent](https://python.langchain.com/docs/modules/agents/)
- [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)
- [DeepSeek 文档](https://platform.deepseek.com/docs)

---

**上一篇：[容错处理实现](./06-容错处理实现.md)** ←

---

**持续更新中...** 📝
