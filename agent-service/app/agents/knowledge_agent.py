"""
知识库 Agent 模块（优化版 v4）

负责：
- 从知识库检索相关信息
- 结合检索结果生成回答
- 返回找到的文章信息（带分类和标签）
- 集成容错处理
- 使用结构化 Prompt 构建
- 集成对话历史管理
- 优化路径显示
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
    知识库 Agent（优化版 v4）
    
    改进点：
    1. 使用结构化 Prompt 构建
    2. 集成对话历史管理
    3. 支持动态阈值和 Top K
    4. 集成容错处理
    5. 优化路径显示（只显示相对路径）
    6. 显示分类和标签信息
    """
    
    async def search_and_answer(
        self,
        query: str,
        session_id: str = None,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        搜索知识库并生成回答（简单版本）
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
        """
        logger.info(f"知识库查询: {query[:50]}...")
        
        # 1. 获取对话历史
        history = None
        if session_id:
            history = await history_manager.get_history(session_id)
        
        # 2. 检索相关文档
        async with async_session_maker() as db:
            search_results = await retriever.search(db, query, dynamic=True)
        
        # 3. 如果没有找到结果，触发容错处理
        if not search_results:
            logger.info(f"知识库无匹配，触发容错处理")
            
            yield {
                "type": "info",
                "message": "📚 在知识库中未找到相关信息"
            }
            
            async for msg in error_handler.handle_no_results(query):
                yield msg
            
            return
        
        # 4. 发送找到的文章信息（带分类和标签）
        articles_info = []
        seen_sources = set()
        for i, result in enumerate(search_results, 1):
            source = result.metadata.get("_source", "未知来源")
            score = result.score
            
            # 去重显示来源
            if source not in seen_sources:
                seen_sources.add(source)
                
                # 提取元数据
                categories = result.metadata.get("categories", [])
                tags = result.metadata.get("tags", [])
                title = result.metadata.get("title", "")
                
                # 提取相对路径
                article_name = self._extract_relative_path(source)
                
                # 构建显示名称（带分类）
                display_name = article_name
                if categories:
                    categories_str = "/".join(categories)
                    display_name = f"[{categories_str}] {article_name}"
                
                articles_info.append({
                    "index": i,
                    "source": source,
                    "name": display_name,
                    "relative_path": article_name,
                    "categories": categories,
                    "tags": tags,
                    "title": title,
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
    
    def _extract_relative_path(self, source: str) -> str:
        """
        提取相对路径（从 _posts 开始）
        """
        
        posts_marker = "_posts/"
        posts_index = source.find(posts_marker)
        
        if posts_index != -1:
            relative_path = source[posts_index + len(posts_marker):]
        else:
            relative_path = source.split("/")[-1] if "/" in source else source
        
        if relative_path.endswith(".md"):
            relative_path = relative_path[:-3]
        
        import urllib.parse
        relative_path = urllib.parse.unquote(relative_path)
        
        return relative_path
    
    def _build_context(self, results: List[SearchResult]) -> str:
        """
        构建检索上下文（带分类信息）
        """
        context_parts = []
        
        for i, result in enumerate(results, 1):
            source = result.metadata.get("_source", "未知来源")
            relative_path = self._extract_relative_path(source)
            categories = result.metadata.get("categories", [])
            
            # 构建来源显示
            if categories:
                categories_str = "/".join(categories)
                source_display = f"[{categories_str}] {relative_path}"
            else:
                source_display = relative_path
            
            context_parts.append(f"[参考资料 {i}] (来源: {source_display})\n{result.content}")
        
        return "\n\n".join(context_parts)


# 全局知识库 Agent 实例
knowledge_agent = KnowledgeAgent()
