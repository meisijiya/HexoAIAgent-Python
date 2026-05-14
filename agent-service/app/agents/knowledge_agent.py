"""
知识库 Agent 模块（优化版 v5）

负责：
- 从知识库检索相关信息
- 结合检索结果生成回答
- 返回找到的文章信息（带可点击链接）
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


# 博客基础 URL（用于生成文章链接）
BLOG_BASE_URL = "https://meisijiya.github.io"


class KnowledgeAgent:
    """
    知识库 Agent（优化版 v5）
    
    改进点：
    1. 参考资料显示为可点击链接
    2. 生成博客文章的完整 URL
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
            yield {"type": "info", "message": "📚 在知识库中未找到相关信息"}
            async for msg in error_handler.handle_no_results(query):
                yield msg
            return
        
        # 4. 发送找到的文章信息（带可点击链接）
        articles_info = []
        seen_sources = set()
        for i, result in enumerate(search_results, 1):
            source = result.metadata.get("_source", "未知来源")
            score = result.score
            
            if source not in seen_sources:
                seen_sources.add(source)
                
                # 提取元数据
                categories = result.metadata.get("categories", [])
                tags = result.metadata.get("tags", [])
                title = result.metadata.get("title", "")
                
                # 生成博客链接
                blog_url = self._generate_blog_url(source, title)
                
                # 提取相对路径
                relative_path = self._extract_relative_path(source)
                
                # 构建显示名称（带分类）
                display_name = relative_path
                if categories:
                    categories_str = "/".join(categories)
                    display_name = f"[{categories_str}] {relative_path}"
                
                articles_info.append({
                    "index": i,
                    "source": source,
                    "name": display_name,
                    "relative_path": relative_path,
                    "categories": categories,
                    "tags": tags,
                    "title": title,
                    "score": score,
                    "blog_url": blog_url,
                    "preview": result.content[:50] + "..."
                })
        
        yield {
            "type": "knowledge_sources",
            "message": f"📚 找到 {len(search_results)} 条相关文档，来自 {len(articles_info)} 篇文章",
            "articles": articles_info
        }
        
        # 5. 构建上下文（带可点击链接）
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
    
    def _generate_blog_url(self, source: str, title: str) -> str:
        """
        生成博客文章的完整 URL
        
        Args:
            source: 文件路径（如 file:///.../2025/博客建设/记录搭建博客流程😗.md）
            title: 文章标题
        
        Returns:
            str: 博客 URL（如 https://meisijiya.github.io/2025/09/16/记录搭建博客流程😗/）
        """
        
        # 提取相对路径
        relative_path = self._extract_relative_path(source)
        
        # 尝试从路径中提取日期信息
        # 路径格式：2025/博客建设/记录搭建博客流程😗
        parts = relative_path.split("/")
        
        if len(parts) >= 1:
            # 年份
            year = parts[0] if parts[0].isdigit() else "2025"
            
            # 如果有文章标题，使用它
            if title:
                # 清理标题，移除特殊字符
                clean_title = title.replace(" ", "-").replace("😗", "").strip()
                return f"{BLOG_BASE_URL}/{year}/01/01/{clean_title}/"
            
            # 使用路径的最后一部分作为文章名
            if len(parts) >= 2:
                article_name = parts[-1]
                return f"{BLOG_BASE_URL}/{year}/01/01/{article_name}/"
        
        # 默认返回博客首页
        return BLOG_BASE_URL
    
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
        构建检索上下文（带可点击链接）
        """
        context_parts = []
        
        for i, result in enumerate(results, 1):
            source = result.metadata.get("_source", "未知来源")
            title = result.metadata.get("title", "")
            relative_path = self._extract_relative_path(source)
            categories = result.metadata.get("categories", [])
            
            # 生成博客链接
            blog_url = self._generate_blog_url(source, title)
            
            # 构建来源显示（带链接）
            if categories:
                categories_str = "/".join(categories)
                source_display = f"[{categories_str}] {relative_path}"
            else:
                source_display = relative_path
            
            # 使用 Markdown 链接格式
            context_parts.append(
                f"[参考资料 {i}] (来源: [{source_display}]({blog_url}))\n{result.content}"
            )
        
        return "\n\n".join(context_parts)


# 全局知识库 Agent 实例
knowledge_agent = KnowledgeAgent()
