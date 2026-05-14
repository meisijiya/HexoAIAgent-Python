"""
知识库 Agent 模块（优化版 v2）

负责：
- 从知识库检索相关信息
- 结合检索结果生成回答
- 返回找到的文章信息
- 集成容错处理
- 使用结构化 Prompt 构建
- 集成对话历史管理
"""
from typing import AsyncGenerator, List, Dict, Any
from loguru import logger

from app.core.llm import llm_client
from app.core.prompt_builder import knowledge_prompt_builder
from app.core.history_manager import history_manager
from app.knowledge.retriever import retriever, SearchResult
from app.core.database import async_session_maker
from app.agents.error_handler import error_handler


class KnowledgeAgent:
    """
    知识库 Agent（优化版 v2）
    
    改进点：
    1. 使用结构化 Prompt 构建
    2. 集成对话历史管理
    3. 支持动态阈值和 Top K
    4. 集成容错处理
    """
    
    async def search_and_answer(
        self,
        query: str,
        session_id: str = None,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        搜索知识库并生成回答（简单版本）
        
        Args:
            query: 用户查询
            session_id: 会话 ID（用于获取历史）
            stream: 是否流式输出
        
        Yields:
            str: 回复内容片段
        """
        async for msg in self.search_and_answer_with_info(query, session_id, stream):
            if msg["type"] == "content":
                yield msg["content"]
    
    async def search_and_answer_with_info(
        self,
        query: str,
        session_id: str = None,
        stream: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        搜索知识库并生成回答（带详细信息）
        
        Args:
            query: 用户查询
            session_id: 会话 ID（用于获取历史）
            stream: 是否流式输出
        
        Yields:
            Dict: 包含类型、内容、找到的文章等信息
        """
        logger.info(f"知识库查询: {query[:50]}...")
        
        # 1. 获取对话历史
        history = None
        if session_id:
            history = await history_manager.get_history(session_id)
        
        # 2. 检索相关文档（使用动态参数）
        async with async_session_maker() as db:
            search_results = await retriever.search(db, query, dynamic=True)
        
        # 3. 如果没有找到结果，触发容错处理
        if not search_results:
            logger.info(f"知识库无匹配，触发容错处理")
            
            yield {
                "type": "info",
                "message": "📚 在知识库中未找到相关信息"
            }
            
            # 调用容错处理器
            async for msg in error_handler.handle_no_results(query):
                yield msg
            
            return
        
        # 4. 发送找到的文章信息
        articles_info = []
        seen_sources = set()
        for i, result in enumerate(search_results, 1):
            source = result.metadata.get("_source", "未知来源")
            score = result.score
            
            # 去重显示来源
            if source not in seen_sources:
                seen_sources.add(source)
                # 从 URL 提取文章名
                article_name = source.split("/")[-1] if "/" in source else source
                if article_name.endswith(".md"):
                    article_name = article_name[:-3]  # 去掉 .md 后缀
                articles_info.append({
                    "index": i,
                    "source": source,
                    "name": article_name,
                    "score": score,
                    "preview": result.content[:50] + "..."
                })
        
        yield {
            "type": "knowledge_sources",
            "message": f"📚 找到 {len(search_results)} 条相关文档，来自 {len(articles_info)} 篇文章",
            "articles": articles_info
        }
        
        # 5. 构建上下文
        rag_context = self._build_context(search_results)
        
        # 6. 使用 Prompt 构建器生成 Prompt
        prompt = knowledge_prompt_builder.build_for_knowledge(
            user_input=query,
            rag_context=rag_context,
            history=history
        )
        
        # 7. 构建消息列表
        messages = [{"role": "user", "content": prompt}]
        
        # 8. 调用 LLM 生成回答
        full_response = ""
        
        if stream:
            async for chunk in llm_client.chat_stream(messages):
                full_response += chunk
                yield {"type": "content", "content": chunk}
        else:
            response = await llm_client.chat(messages)
            full_response = response
            yield {"type": "content", "content": response}
        
        # 9. 保存到历史
        if session_id:
            await history_manager.save_message(session_id, "user", query)
            await history_manager.save_message(session_id, "assistant", full_response)
        
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
