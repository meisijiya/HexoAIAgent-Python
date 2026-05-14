"""
知识库 Agent 模块

负责：
- 从知识库检索相关信息
- 结合检索结果生成回答
"""
from typing import AsyncGenerator, List, Dict
from loguru import logger

from app.core.llm import llm_client
from app.knowledge.retriever import retriever, SearchResult
from app.core.database import async_session_maker


# 系统提示词
KNOWLEDGE_PROMPT = """你是一个专业的知识库助手，专门根据提供的参考资料回答问题。

你的任务：
1. 仔细阅读参考资料
2. 基于参考资料回答用户问题
3. 如果参考资料中没有相关信息，诚实地说不知道
4. 回答要准确、简洁
5. 引用参考资料时注明来源

请用中文回复。"""


class KnowledgeAgent:
    """
    知识库 Agent
    
    从知识库检索相关信息并生成回答
    """
    
    async def search_and_answer(
        self,
        query: str,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        搜索知识库并生成回答
        
        Args:
            query: 用户查询
            stream: 是否流式输出
        
        Yields:
            str: 回复内容片段
        """
        logger.info(f"知识库查询: {query[:50]}...")
        
        # 检索相关文档
        async with async_session_maker() as db:
            search_results = await retriever.search(db, query, top_k=3)
        
        if not search_results:
            yield "抱歉，知识库中没有找到相关信息。"
            return
        
        # 构建上下文
        context = self._build_context(search_results)
        
        # 构建消息
        messages = [
            {"role": "system", "content": KNOWLEDGE_PROMPT},
            {"role": "user", "content": f"参考资料：\n{context}\n\n用户问题：{query}"}
        ]
        
        # 调用 LLM 生成回答
        full_response = ""
        
        if stream:
            async for chunk in llm_client.chat_stream(messages):
                full_response += chunk
                yield chunk
        else:
            response = await llm_client.chat(messages)
            full_response = response
            yield response
        
        logger.info(f"知识库回答完成: {full_response[:50]}...")
    
    def _build_context(self, results: List[SearchResult]) -> str:
        """
        构建检索上下文
        
        Args:
            results: 搜索结果列表
        
        Returns:
            str: 格式化的上下文文本
        """
        context_parts = []
        
        for i, result in enumerate(results, 1):
            source = result.metadata.get("_source", "未知来源")
            context_parts.append(f"[参考资料 {i}] (来源: {source})\n{result.content}")
        
        return "\n\n".join(context_parts)


# 全局知识库 Agent 实例
knowledge_agent = KnowledgeAgent()
