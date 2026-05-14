"""
搜索 Agent 模块（优化版）

负责：
- 调用外部搜索 API
- 整理搜索结果
- 生成回答
- 集成对话历史管理
"""
from typing import AsyncGenerator, List, Dict
import httpx
from loguru import logger

from app.core.llm import llm_client
from app.core.history_manager import history_manager


# 系统提示词
SEARCH_PROMPT = """你是一个专业的搜索助手，专门根据搜索结果回答问题。

你的任务：
1. 仔细阅读搜索结果
2. 基于搜索结果回答用户问题
3. 提供准确、有用的信息
4. 引用信息来源
5. 如果搜索结果中没有相关信息，诚实地说不知道

请用中文回复。"""


class SearchAgent:
    """
    搜索 Agent（优化版）
    
    改进点：
    1. 集成对话历史管理
    2. 支持上下文理解
    """
    
    def __init__(self):
        """初始化搜索 Agent"""
        self.search_url = "https://api.duckduckgo.com/"
    
    async def search_and_answer(
        self,
        query: str,
        session_id: str = None,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        搜索并生成回答
        
        Args:
            query: 用户查询
            session_id: 会话 ID（用于获取历史）
            stream: 是否流式输出
        
        Yields:
            str: 回复内容片段
        """
        logger.info(f"搜索查询: {query[:50]}...")
        
        # 1. 获取对话历史
        history = ""
        if session_id:
            history = await history_manager.get_history(session_id)
        
        # 2. 执行搜索
        search_results = await self._search(query)
        
        if not search_results:
            yield "抱歉，没有找到相关的搜索结果。"
            return
        
        # 3. 构建上下文
        context = self._build_context(search_results)
        
        # 4. 构建消息（带历史）
        system_content = SEARCH_PROMPT
        if history:
            system_content += f"\n\n## 对话历史\n{history}"
        
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": f"搜索结果：\n{context}\n\n用户问题：{query}"}
        ]
        
        # 5. 调用 LLM 生成回答
        full_response = ""
        
        if stream:
            async for chunk in llm_client.chat_stream(messages):
                full_response += chunk
                yield chunk
        else:
            response = await llm_client.chat(messages)
            full_response = response
            yield response
        
        # 6. 保存到历史
        if session_id:
            await history_manager.save_message(session_id, "user", query)
            await history_manager.save_message(session_id, "assistant", full_response)
        
        logger.info(f"搜索回答完成: {full_response[:50]}...")
    
    async def _search(self, query: str) -> List[Dict[str, str]]:
        """
        执行搜索
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    self.search_url,
                    params={
                        "q": query,
                        "format": "json",
                        "no_html": 1,
                        "skip_disambig": 1
                    },
                    timeout=10.0
                )
                
                if response.status_code != 200:
                    logger.error(f"搜索 API 调用失败: {response.status_code}")
                    return []
                
                data = response.json()
                results = []
                
                if data.get("Abstract"):
                    results.append({
                        "title": data.get("Heading", ""),
                        "content": data["Abstract"],
                        "url": data.get("AbstractURL", "")
                    })
                
                for topic in data.get("RelatedTopics", [])[:3]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        results.append({
                            "title": topic.get("Text", "")[:50],
                            "content": topic["Text"],
                            "url": topic.get("FirstURL", "")
                        })
                
                logger.info(f"搜索完成: '{query[:30]}...', 找到 {len(results)} 条结果")
                return results
                
            except Exception as e:
                logger.error(f"搜索失败: {e}")
                return []
    
    def _build_context(self, results: List[Dict[str, str]]) -> str:
        """
        构建搜索上下文
        """
        context_parts = []
        
        for i, result in enumerate(results, 1):
            url = result.get("url", "")
            context_parts.append(f"[搜索结果 {i}] (来源: {url})\n{result['content']}")
        
        return "\n\n".join(context_parts)


# 全局搜索 Agent 实例
search_agent = SearchAgent()
