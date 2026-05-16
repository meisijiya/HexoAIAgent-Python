"""
工具定义和调用模块（重构版 v2）

职责：
- 定义可用工具
- 工具调用执行
- 工具结果格式化

变更：
- 移除知识库工具（与 KnowledgeAgent 重复）
- 添加 WebSearchTool（支持百度/DuckDuckGo）
- ReAct Agent 使用 web_search 进行网络搜索
"""
import os
import json
from typing import Dict, Any, List, Optional
import httpx
from loguru import logger


class Tool:
    """工具基类"""
    
    def __init__(self, name: str, description: str, parameters: Dict[str, Any]):
        self.name = name
        self.description = description
        self.parameters = parameters
    
    async def execute(self, **kwargs) -> str:
        """执行工具"""
        raise NotImplementedError


class WebSearchTool(Tool):
    """网络搜索工具（支持百度/DuckDuckGo）"""
    
    def __init__(self):
        super().__init__(
            name="web_search",
            description="使用搜索引擎进行网络搜索，获取最新信息",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询词，例如：2025年最新AI新闻、Python异步编程教程"
                    }
                },
                "required": ["query"]
            }
        )
        # 搜索引擎配置
        self.search_engine = os.getenv("SEARCH_ENGINE", "baidu")
        self.baidu_api_key = os.getenv("BAIDU_SEARCH_API_KEY", "")
    
    async def execute(self, query: str = "", **kwargs) -> str:
        """执行网络搜索"""
        if not query:
            return "错误：缺少搜索查询参数"
        
        # 根据配置选择搜索引擎
        if self.search_engine == "baidu" and self.baidu_api_key:
            return await self._search_baidu(query)
        else:
            return await self._search_duckduckgo(query)
    
    async def _search_baidu(self, query: str) -> Dict[str, Any]:
        """使用百度千帆搜索 API"""
        if not self.baidu_api_key:
            return {"summary": "错误：百度搜索 API Key 未配置", "sources": []}
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://qianfan.baidubce.com/v2/ai_search/web_search",
                    json={
                        "messages": [
                            {
                                "role": "user",
                                "content": query
                            }
                        ],
                        "search_source": "baidu_search_v2",
                        "resource_type_filter": [
                            {"type": "web", "top_k": 5}
                        ],
                        "search_recency_filter": "year"
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.baidu_api_key}"
                    },
                    timeout=15.0
                )
                
                if response.status_code != 200:
                    logger.warning(f"百度搜索 HTTP {response.status_code}，尝试回退到 DuckDuckGo")
                    return await self._search_duckduckgo(query)
                
                data = response.json()
                references = data.get("references", [])
                
                if not references:
                    return {"summary": f"搜索'{query}'没有找到相关结果", "sources": []}
                
                formatted = []
                sources = []
                for i, ref in enumerate(references[:5], 1):
                    title = ref.get("title", "")
                    url = ref.get("url", "")
                    content = ref.get("content", "")[:200]
                    formatted.append(f"[{i}] {title}\n    链接: {url}\n    摘要: {content}...")
                    sources.append({"title": title, "url": url, "snippet": content})
                
                return {"summary": "\n\n".join(formatted), "sources": sources}
                
        except Exception as e:
            logger.error(f"百度搜索失败: {e}")
            return {"summary": f"百度搜索失败：{str(e)}", "sources": []}
    
    async def _search_duckduckgo(self, query: str) -> Dict[str, Any]:
        """使用 DuckDuckGo 搜索（备用）"""
        try:
            from duckduckgo_search import DDGS
            
            logger.info(f"执行 DuckDuckGo 搜索: {query}")
            
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            
            if not results:
                return {"summary": f"搜索'{query}'没有找到相关结果", "sources": []}
            
            formatted = []
            sources = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "")
                href = r.get("href", "")
                body = r.get("body", "")
                formatted.append(f"[{i}] {title}\n    链接: {href}\n    摘要: {body[:200]}...")
                sources.append({"title": title, "url": href, "snippet": body[:200]})
            
            return {"summary": "\n\n".join(formatted), "sources": sources}
            
        except ImportError:
            logger.error("duckduckgo_search 未安装")
            return {"summary": "错误：搜索服务不可用（缺少依赖）", "sources": []}
        except Exception as e:
            logger.error(f"DuckDuckGo 搜索失败: {e}")
            return {"summary": f"DuckDuckGo 搜索失败：{str(e)}", "sources": []}


class KnowledgeSearchTool(Tool):
    """知识库搜索工具，检索本地知识库中的技术文档和教程片段"""

    def __init__(self):
        super().__init__(
            name="knowledge_search",
            description="搜索本地知识库，获取技术文档和教程的原文片段",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询词，例如：Hexo部署流程、Markdown语法、插件开发"
                    }
                },
                "required": ["query"]
            }
        )

    async def execute(self, query: str = "", **kwargs) -> str:
        """执行知识库搜索，返回原文片段及其相似度分数"""
        if not query:
            return "错误：缺少搜索查询参数"

        from app.core.database import async_session_maker
        from app.knowledge.retriever import retriever

        async with async_session_maker() as db:
            try:
                results = await retriever.search(db, query, top_k=5, dynamic=True)

                if not results:
                    return f"知识库搜索「{query}」没有找到相关结果"

                formatted = []
                for i, r in enumerate(results, 1):
                    formatted.append(
                        f"[{i}] (相似度: {r.score:.4f})\n"
                        f"    {r.content.strip()}"
                    )

                return "\n\n".join(formatted)

            except Exception as e:
                logger.error(f"知识库搜索失败: {e}")
                return f"知识库搜索失败：{str(e)}"


class ToolCollection:
    """工具集合"""
    
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self._register_default_tools()
    
    def _register_default_tools(self):
        """注册默认工具"""
        self.register(WebSearchTool())
        self.register(KnowledgeSearchTool())
    
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
            return f"错误：工具 '{tool_name}' 不存在。可用工具：{', '.join(self.tools.keys())}"
        
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
