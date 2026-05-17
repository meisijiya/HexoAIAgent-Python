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
from app.config import settings


# 博客基础 URL（从环境变量 BLOG_BASE_URL 读取）
BLOG_BASE_URL = settings.BLOG_BASE_URL or "https://meisijiya.github.io"


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
        
        # 2.5 LLM 辅助相关性筛选（有过滤条件且候选结果 > 3 时，让 LLM 挑真正相关的）
        if (categories or tags) and len(search_results) > 3:
            search_results = await self._llm_filter_relevant(search_results, query)
        
        # 3. 知识库无匹配或相似度过低 → 尝试分类/标签列表（如有过滤条件）
        max_score = max((r.score for r in search_results), default=0)
        if (not search_results or max_score < 0.6) and (categories or tags):
            from sqlalchemy import select as sa_select, text as sa_text
            from app.models.knowledge import Article as KA
            filter_parts = []
            if categories:
                escaped = [c.replace("'", "''") for c in categories]
                filter_parts.append(f"c.metadata->'categories' ?| ARRAY{escaped}")
            if tags:
                escaped = [t.replace("'", "''") for t in tags]
                filter_parts.append(f"EXISTS (SELECT 1 FROM jsonb_array_elements_text(c.metadata->'tags') elem WHERE LOWER(elem) IN ({','.join('LOWER(' + chr(39) + t + chr(39) + ')' for t in escaped)}))")
            filter_sql = " AND ".join(filter_parts)
            sql = sa_text(f"""
                SELECT DISTINCT ON (a.id) a.id, a.title, a.url,
                       c.metadata->'categories' as categories,
                       c.metadata->'tags' as tags
                FROM knowledge_articles a
                JOIN knowledge_chunks c ON c.article_id = a.id
                WHERE {filter_sql}
                LIMIT 20
            """)
            async with async_session_maker() as db2:
                result = await db2.execute(sql)
                rows = result.fetchall()
            if rows:
                articles = [{"name": f"{' / '.join(r.categories) if r.categories else '?'} | {r.title}",
                            "title": r.title, "blog_url": r.url,
                            "score": 1.0} for r in rows]
                yield {"type": "knowledge_sources", "message": f"📋 {categories[0] if categories else tags[0]} 分类共 {len(articles)} 篇文章",
                       "articles": articles}
                cat_label = categories[0] if categories else (tags[0] if tags else "")
                fallback_prompt = f"""以下是{cat_label}分类下的文章列表。请用中文简要介绍这些文章，并引导用户提问。

{chr(10).join(f'- {a["title"]} ({a["blog_url"]})' for a in articles)}

用户问：{query}"""
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
    
    async def _llm_filter_relevant(self, results, query):
        """
        LLM 辅助相关性筛选：从语义搜索候选集中挑出真正相关的文章

        触发条件：用户指定了分类/标签过滤，且候选结果 > 3 个时。
        向量余弦相似度只能反映"文本像不像"，但无法理解用户真正意图。
        LLM 可以判断"java分类下分布式锁"应该保留《06-分布式锁》
        而丢弃《Mybatis快速上手》，即使两者都包含 Java 相关词汇。

        Token 消耗：~200 in / ~20 out，轻量调用。

        Args:
            results: 语义搜索候选结果 (List[SearchResult])
            query: 用户原始问题

        Returns:
            过滤后的结果列表
        """
        # 构建候选清单：序号 + 标题 + 简短摘要
        candidates = []
        index_map = {}  # 候选序号 → 原 SearchResult
        seen_titles = set()
        for i, r in enumerate(results):
            title = r.metadata.get("title", "")
            if title in seen_titles:
                continue
            seen_titles.add(title)
            idx = len(candidates)
            candidates.append(f"{idx}: {title}（摘要：{r.content[:60]}...）")
            index_map[idx] = r

        if len(candidates) <= 3:
            return results  # ≤3 个候选，没必要让 LLM 筛

        prompt = f"""你是相关性筛选器。用户问了：「{query}」

候选文章列表（格式：序号: 标题（摘要））：
{chr(10).join(candidates)}

请只返回真正与用户问题相关的文章序号（用逗号分隔，如 0,2,5）。
无关的不要返回。如果全都不相关，返回空。
只返回序号，不要其他内容。"""

        try:
            response = await llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0, max_tokens=50
            )
            # 解析 LLM 返回的序号列表
            import re
            indices = [int(n) for n in re.findall(r'\d+', response)]
            filtered = [index_map[i] for i in indices if i in index_map]
            if filtered:
                logger.info(f"LLM 筛选：{len(results)} → {len(filtered)} 条相关结果")
                return filtered
        except Exception as e:
            logger.warning(f"LLM 筛选失败，回退到全量结果: {e}")

        return results  # 失败或全不相关时回退

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
