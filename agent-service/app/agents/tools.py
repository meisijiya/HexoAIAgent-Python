"""
工具定义和调用模块

负责：
- 定义可用工具
- 工具调用执行
- 工具结果格式化
"""
import json
from typing import Dict, Any, List, Callable, Optional
from loguru import logger

from app.knowledge.retriever import retriever
from app.core.database import async_session_maker


class Tool:
    """工具基类"""
    
    def __init__(self, name: str, description: str, parameters: Dict[str, Any]):
        self.name = name
        self.description = description
        self.parameters = parameters
    
    async def execute(self, **kwargs) -> str:
        """执行工具"""
        raise NotImplementedError


class SearchKnowledgeTool(Tool):
    """知识库搜索工具"""
    
    def __init__(self):
        super().__init__(
            name="search_knowledge",
            description="搜索知识库中的文档，获取技术文档和教程信息",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询，例如：Redis 分布式锁、Hexo 安装"
                    }
                },
                "required": ["query"]
            }
        )
    
    async def execute(self, query: str = "", **kwargs) -> str:
        """执行知识库搜索"""
        if not query:
            return "错误：缺少搜索查询参数"
        
        try:
            async with async_session_maker() as db:
                results = await retriever.search(db, query, top_k=3, dynamic=False)
            
            if not results:
                return f"知识库中没有找到关于"{query}"的相关文档"
            
            # 格式化结果
            formatted = []
            for i, r in enumerate(results, 1):
                source = r.metadata.get("_source", "未知来源")
                formatted.append(f"[{i}] (来源: {source})\n{r.content[:200]}...")
            
            return "\n\n".join(formatted)
            
        except Exception as e:
            logger.error(f"知识库搜索失败: {e}")
            return f"知识库搜索失败：{str(e)}"


class GetArticleTool(Tool):
    """获取文章工具"""
    
    def __init__(self):
        super().__init__(
            name="get_article",
            description="获取指定文章的详细内容",
            parameters={
                "type": "object",
                "properties": {
                    "article_title": {
                        "type": "string",
                        "description": "文章标题或关键词"
                    }
                },
                "required": ["article_title"]
            }
        )
    
    async def execute(self, article_title: str = "", **kwargs) -> str:
        """获取文章内容"""
        if not article_title:
            return "错误：缺少文章标题参数"
        
        try:
            from app.models.knowledge import Article
            from sqlalchemy import select
            
            async with async_session_maker() as db:
                # 模糊搜索文章
                result = await db.execute(
                    select(Article).where(
                        Article.title.ilike(f"%{article_title}%")
                    )
                )
                articles = result.scalars().all()
                
                if not articles:
                    return f"没有找到标题包含"{article_title}"的文章"
                
                # 返回第一篇文章
                article = articles[0]
                return f"标题：{article.title}\n\n内容：\n{article.content[:1000]}..."
                
        except Exception as e:
            logger.error(f"获取文章失败: {e}")
            return f"获取文章失败：{str(e)}"


class ListArticlesTool(Tool):
    """列出文章工具"""
    
    def __init__(self):
        super().__init__(
            name="list_articles",
            description="列出知识库中的所有文章标题",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    
    async def execute(self, **kwargs) -> str:
        """列出所有文章"""
        try:
            from app.models.knowledge import Article
            from sqlalchemy import select
            
            async with async_session_maker() as db:
                result = await db.execute(
                    select(Article.title).order_by(Article.created_at.desc())
                )
                titles = [row[0] for row in result.fetchall()]
                
                if not titles:
                    return "知识库中暂无文章"
                
                # 格式化文章列表
                formatted = [f"[{i+1}] {title}" for i, title in enumerate(titles[:20])]
                return f"知识库共有 {len(titles)} 篇文章：\n" + "\n".join(formatted)
                
        except Exception as e:
            logger.error(f"列出文章失败: {e}")
            return f"列出文章失败：{str(e)}"


class ToolCollection:
    """工具集合"""
    
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self._register_default_tools()
    
    def _register_default_tools(self):
        """注册默认工具"""
        self.register(SearchKnowledgeTool())
        self.register(GetArticleTool())
        self.register(ListArticlesTool())
    
    def register(self, tool: Tool):
        """注册工具"""
        self.tools[tool.name] = tool
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """获取工具"""
        return self.tools.get(name)
    
    def get_tools_description(self) -> str:
        """获取所有工具的描述（用于 Prompt）"""
        descriptions = []
        for tool in self.tools.values():
            desc = f"- {tool.name}: {tool.description}"
            if tool.parameters.get("properties"):
                params = ", ".join(tool.parameters["properties"].keys())
                desc += f"\n  参数: {params}"
            descriptions.append(desc)
        
        return "\n".join(descriptions)
    
    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """获取所有工具的 JSON Schema（用于 Function Call）"""
        schemas = []
        for tool in self.tools.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            })
        return schemas
    
    async def call(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """调用工具"""
        tool = self.get_tool(tool_name)
        
        if not tool:
            return f"错误：工具 "{tool_name}" 不存在。可用工具：{', '.join(self.tools.keys())}"
        
        try:
            logger.info(f"调用工具: {tool_name}, 参数: {tool_input}")
            result = await tool.execute(**tool_input)
            logger.info(f"工具调用完成: {tool_name}, 结果长度: {len(result)}")
            return result
        except Exception as e:
            logger.error(f"工具调用失败: {tool_name}, 错误: {e}")
            return f"工具调用失败：{str(e)}"


# 全局工具集合实例
tool_collection = ToolCollection()
