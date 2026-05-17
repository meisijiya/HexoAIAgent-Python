"""
知识库 Agent 模块（优化版 v6）

负责：
- 从知识库检索相关信息
- 结合检索结果生成回答
- 返回找到的文章信息（带可点击链接）
- 知识库无匹配时自动 fallback 到 LLM 自身知识
- 提示用户是否需要上网搜索（立即显示选项）
- 使用结构化 Prompt 构建
- 集成对话历史管理
"""
from typing import AsyncGenerator, List, Dict, Any, Optional
from loguru import logger

from app.core.llm import llm_client
from app.core.prompt_builder import knowledge_prompt_builder
from app.core.history_manager import history_manager
from app.knowledge.retriever import retriever, SearchResult
from app.core.database import async_session_maker


# 博客基础 URL（用于生成文章链接，可通过环境变量 BLOG_BASE_URL 覆盖）
BLOG_BASE_URL = "https://meisijiya.github.io"


class KnowledgeAgent:
    """
    知识库 Agent（优化版 v6）
    
    改进点：
    1. 参考资料显示为可点击链接
    2. 生成博客文章的完整 URL
    3. 知识库无匹配时自动 fallback 到 LLM 自身知识
    4. 提示用户是否需要上网搜索（立即显示选项）
    """
    
    async def process(
        self,
        message: str,
        session_id: str = None,
        stream: bool = True,
        db=None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理用户消息（Orchestrator 调用入口）
        
        Args:
            message: 用户消息
            session_id: 会话 ID
            stream: 是否流式输出
            db: 数据库会话（用于语义记忆检索）
            filters: 可选，检索过滤条件 {"categories": [...], "tags": [...]}
            
        Yields:
            Dict[str, Any]: 处理结果
        """
        yield {"type": "routing", "agent": "knowledge", "message": "正在检索知识库..."}
        async for msg in self.search_and_answer_with_info(message, session_id, stream, db=db, filters=filters):
             yield msg
    
    async def search_and_answer(
        self,
        query: str,
        session_id: str = None,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """搜索知识库并生成回答（简单版本）"""
        async for msg in self.search_and_answer_with_info(query, session_id, stream):
            if msg["type"] == "content":
                yield msg["content"]
    
    async def search_and_answer_with_info(
        self,
        query: str,
        session_id: str = None,
        stream: bool = True,
        db=None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """搜索知识库并生成回答（带详细信息）"""
        logger.info(f"知识库查询: {query[:50]}...")
        
        # 1. 获取对话历史（传递 db 用于语义记忆检索）
        history = None
        if session_id:
            history = await history_manager.get_history(session_id, query=query, db=db)
        
        # 2. 检索相关文档（支持分类/标签过滤）
        categories = filters.get("categories") if filters else None
        tags = filters.get("tags") if filters else None
        async with async_session_maker() as db:
            search_results = await retriever.search(
                db, query, dynamic=True, categories=categories, tags=tags
            )
        
        # 3. 知识库无匹配或相似度过低 → 提示用户 + fallback 到 LLM 自身知识
        max_score = max((r.score for r in search_results), default=0)
        if not search_results or max_score < 0.6:
            logger.info(f"知识库无匹配，提示用户选择是否上网搜索")
            
            yield {"type": "info", "message": "知识库未找到相关内容"}
            yield {
                "type": "options",
                "options": [
                    {"label": "上网搜索", "value": "search", "icon": "🔍"},
                    {"label": "算了", "value": "done", "icon": "✅"}
                ]
            }
            
            fallback_prompt = f"""请用你的知识回答以下问题。如果不确定，请说明。

问题：{query}

请用中文回答，简洁明了。"""
            
            messages = [{"role": "user", "content": fallback_prompt}]
            full_response = ""
            
            if stream:
                async for chunk in llm_client.chat_stream(messages):
                    full_response += chunk
                    yield {"type": "content", "content": chunk}
            else:
                response = await llm_client.chat(messages)
                full_response = response
                yield {"type": "content", "content": response}
            
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
                title = result.metadata.get("title", "未命名文章")
                
                # 博客链接：优先从 metadata 的 _source（已是 blog URL）或 date+title 构建
                blog_url = result.metadata.get("_source", "")
                if not blog_url or "file://" in blog_url:
                    blog_url = self._generate_blog_url_from_metadata(result.metadata, title)
                
                # 显示名称
                display_name = title
                if categories:
                    display_name = f"[{'/'.join(categories)}] {title}"
                
                articles_info.append({
                    "index": i,
                    "source": source,
                    "name": display_name,
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
        logger.info(f"知识库回答完成: {full_response[:50]}...")
    
    def _generate_blog_url(self, source: str, title: str, metadata: dict = None) -> str:
        """
        生成博客文章的完整 URL
        
        Hexo permalink: :year/:month/:day/:title/
        其中 :title = 文件相对于 _posts/ 的路径（不含 .md 后缀）
        
        实际 URL 示例：
        https://meisijiya.github.io/2025/09/16/2025/博客建设/记录搭建博客流程😗/
        
        Args:
            source: 文件路径（如 file:///.../2025/博客建设/记录搭建博客流程😗.md）
            title: 文章标题（front-matter 中的 title）
            metadata: chunk 元数据（包含 date、categories 等）
        
        Returns:
            str: 博客 URL
        """
        
        # 从 metadata 中读取日期
        date_str = ""
        if metadata:
            date_str = metadata.get("date", "")
        
        # 解析日期
        year, month, day = "2025", "01", "01"
        if date_str:
            date_str = str(date_str)
            if len(date_str) >= 10:
                parts = date_str[:10].split("-")
                if len(parts) == 3:
                    year, month, day = parts[0], parts[1], parts[2]
        
        # 提取相对路径（从 _posts 开始，不含 .md）
        # 这就是 Hexo 的 :title 部分
        relative_path = self._extract_relative_path(source)
        
        # 构建 URL：/{year}/{month}/{day}/{relative_path}/
        # 需要对路径进行 URL 编码
        import urllib.parse
        encoded_path = urllib.parse.quote(relative_path, safe='/')
        
        return f"{BLOG_BASE_URL}/{year}/{month}/{day}/{encoded_path}/"
    
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
    
    def _generate_blog_url_from_metadata(self, metadata: dict, title: str) -> str:
        """从 chunk metadata 构造博客 URL（当 _source 不可用时 fallback）"""
        date_str = str(metadata.get("date", ""))
        if date_str and len(date_str) >= 10:
            parts = date_str[:10].split("-")
            if len(parts) == 3:
                from urllib.parse import quote
                slug = quote(title.strip(), safe="")
                return f"{BLOG_BASE_URL}/{parts[0]}/{parts[1]}/{parts[2]}/{slug}/"
        return "#"
    
    def _build_context(self, results: List[SearchResult]) -> str:
        """
        构建检索上下文（带可点击链接）
        """
        context_parts = []
        
        for i, result in enumerate(results, 1):
            source = result.metadata.get("_source", "")
            title = result.metadata.get("title", "未命名文章")
            categories = result.metadata.get("categories", [])
            
            # 博客链接
            blog_url = source if (source and "file://" not in source) else self._generate_blog_url_from_metadata(result.metadata, title)
            
            # 构建来源显示
            cats_str = "/".join(categories) if categories else ""
            display = f"[{cats_str}] {title}" if cats_str else title
            
            context_parts.append(
                f"[参考资料 {i}] (来源: [{display}]({blog_url}))\n{result.content}"
            )
        
        return "\n\n".join(context_parts)


# 全局知识库 Agent 实例
knowledge_agent = KnowledgeAgent()
