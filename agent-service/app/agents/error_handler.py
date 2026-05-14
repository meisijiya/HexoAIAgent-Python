"""
容错处理模块

负责：
- 处理知识库无匹配结果的情况
- 引导用户补充问题
- 提供 LLM 参考答案
- 优雅降级
"""
from typing import AsyncGenerator, Dict, Any, List
from loguru import logger

from app.core.llm import llm_client


class ErrorHandler:
    """
    错误处理器
    
    当知识库无匹配时，提供友好的引导和备选方案
    """
    
    async def handle_no_results(self, query: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理无检索结果的情况
        
        Args:
            query: 用户查询
        
        Yields:
            Dict: 包含引导信息和选项
        """
        
        # 分析查询类型
        query_type = self._analyze_query_type(query)
        
        # 生成引导性回复
        if query_type == "technical":
            guidance = self._technical_guidance(query)
        elif query_type == "concept":
            guidance = self._concept_guidance(query)
        else:
            guidance = self._general_guidance(query)
        
        yield {"type": "content", "content": guidance}
        
        # 提供选项
        yield {
            "type": "options",
            "options": [
                {"label": "用你的知识回答", "value": "fallback", "icon": "💡"},
                {"label": "搜索外部资料", "value": "search", "icon": "🔍"},
                {"label": "换个问法", "value": "rephrase", "icon": "✏️"}
            ]
        }
    
    async def handle_user_choice(self, choice: str, query: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理用户选择
        
        Args:
            choice: 用户选择
            query: 原始查询
        
        Yields:
            Dict: 回复内容
        """
        
        if choice == "fallback":
            # 生成参考答案
            async for chunk in self._generate_fallback_answer(query):
                yield chunk
        
        elif choice == "search":
            # 触发搜索
            yield {"type": "trigger_search", "query": query}
        
        elif choice == "rephrase":
            # 提供改写建议
            suggestions = await self._suggest_rephrasing(query)
            content = "你可以试试这样问：\n" + "\n".join(f"- {s}" for s in suggestions)
            yield {"type": "content", "content": content}
    
    def _analyze_query_type(self, query: str) -> str:
        """
        分析查询类型
        """
        
        # 技术关键词
        technical_keywords = [
            "怎么", "如何", "实现", "配置", "部署", "安装", "报错", "错误",
            "bug", "异常", "失败", "不工作", "无效"
        ]
        
        # 概念关键词
        concept_keywords = [
            "是什么", "什么是", "定义", "概念", "原理", "介绍", "了解"
        ]
        
        for keyword in technical_keywords:
            if keyword in query:
                return "technical"
        
        for keyword in concept_keywords:
            if keyword in query:
                return "concept"
        
        return "general"
    
    def _technical_guidance(self, query: str) -> str:
        """技术问题引导"""
        
        return f"""我在知识库中没有找到关于"{query}"的文档。

💡 你可以尝试：

1. **换个问法**：比如把"如何实现X"改成"X的实现步骤是什么"
2. **提供更多细节**：比如你使用的具体技术栈、版本等
3. **搜索相关主题**：输入 `/搜索 {query}` 来查找外部资料

或者，我可以根据我的知识尝试回答，虽然可能不如知识库中的文档准确。"""
    
    def _concept_guidance(self, query: str) -> str:
        """概念问题引导"""
        
        return f"""抱歉，我的知识库中暂时没有关于"{query}"的内容。

📚 我可以帮你：

1. **搜索外部资料**：输入 `/搜索 {query}`
2. **用我的知识回答**：虽然可能不够详细，但可以给你一个基本概念
3. **推荐相关文档**：我可以看看知识库中有没有相关的内容

你想试试哪种方式？"""
    
    def _general_guidance(self, query: str) -> str:
        """通用引导"""
        
        return f"""我没有找到与"{query}"完全匹配的信息。

🔍 建议：
1. 尝试更具体的描述
2. 检查是否有错别字
3. 使用 `/搜索` 命令查找外部资源

需要我尝试用我的知识来回答吗？"""
    
    async def _generate_fallback_answer(self, query: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        生成备选答案
        
        当知识库无匹配时，使用 LLM 自身知识回答
        """
        
        prompt = f"""用户问了一个问题，但知识库中没有找到相关文档。

用户问题：{query}

请根据你的知识，给出一个简洁的回答。

要求：
1. 承认这不是来自官方文档
2. 提供基本的概念解释
3. 建议用户查阅官方文档获取准确信息
4. 保持简洁，不超过 300 字

回答："""
        
        messages = [{"role": "user", "content": prompt}]
        
        # 流式输出
        full_response = ""
        async for chunk in llm_client.chat_stream(messages):
            full_response += chunk
            yield {"type": "content", "content": chunk}
        
        # 添加免责声明
        yield {
            "type": "content", 
            "\n\n⚠️ *以上回答基于 AI 的通用知识，可能不够准确。建议查阅官方文档获取权威信息。*"
        }
    
    async def _suggest_rephrasing(self, query: str) -> List[str]:
        """
        建议改写查询
        """
        
        prompt = f"""用户的问题没有在知识库中找到匹配结果。

用户问题：{query}

请建议 3 个不同的问法，帮助用户更好地表达问题。

要求：
1. 保持原意不变
2. 使用不同的表达方式
3. 更具体或更通用
4. 每行一个建议

建议："""
        
        messages = [{"role": "user", "content": prompt}]
        
        response = await llm_client.chat(messages)
        
        # 解析建议
        suggestions = [
            line.strip().lstrip("0123456789.-) ")
            for line in response.split("\n")
            if line.strip() and len(line.strip()) > 5
        ]
        
        return suggestions[:3]


# 全局错误处理器实例
error_handler = ErrorHandler()
