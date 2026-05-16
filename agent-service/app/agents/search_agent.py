"""
搜索 Agent 模块（优化版 v2）

负责：
- 调用百度千帆搜索 API
- 整理搜索结果
- 生成回答
- 集成对话历史管理
"""
import os
from typing import AsyncGenerator, List, Dict, Any
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
        self.baidu_api_key = os.getenv("BAIDU_SEARCH_API_KEY", "")
        self._search_error = ""  # 搜索错误类型标记
    
    async def process(
        self,
        message: str,
        session_id: str = None,
        stream: bool = True,
        db=None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理用户消息（Orchestrator 调用入口）
        
        Args:
            message: 用户消息
            session_id: 会话 ID
            stream: 是否流式输出
            db: 数据库会话（用于语义记忆检索）
            
        Yields:
            Dict[str, Any]: 处理结果
        """
        yield {"type": "routing", "agent": "search", "message": "正在搜索网络..."}
        async for chunk in self.search_and_answer(message, session_id, stream, db=db):
            # 如果 chunk 已经是 dict 类型（如 info、search_sources），直接 yield
            if isinstance(chunk, dict):
                yield chunk
            else:
                # 否则包装成 content 消息
                yield {"type": "content", "content": chunk}
    
    async def search_and_answer(
        self,
        query: str,
        session_id: str = None,
        stream: bool = True,
        db=None,
    ) -> AsyncGenerator[str, None]:
        """
        搜索并生成回答
        
        Args:
            query: 用户查询
            session_id: 会话 ID（用于获取历史）
            stream: 是否流式输出
            db: 数据库会话（用于语义记忆检索）
        
        Yields:
            str: 回复内容片段
        """
        logger.info(f"搜索查询: {query[:50]}...")
        
        # 1. 获取对话历史（传递 db 用于语义记忆检索）
        history = ""
        if session_id:
            history = await history_manager.get_history(session_id, query=query, db=db)
        
        # 2. 执行搜索
        search_results = await self._search(query)
        
        if not search_results:
            # 搜索失败时，使用 LLM 自身知识回答
            logger.info(f"搜索无结果，使用 LLM 自身知识回答: {query[:50]}...")
            fallback_messages = [
                {"role": "system", "content": "你是一个知识渊博的助手。请用你的知识回答用户的问题。如果不确定，请说明。"},
                {"role": "user", "content": query}
            ]
            fallback_response = ""
            if stream:
                async for chunk in llm_client.chat_stream(fallback_messages):
                    fallback_response += chunk
                    yield chunk
            else:
                fallback_response = await llm_client.chat(fallback_messages)
                yield fallback_response
            
            # 友好提示
            if getattr(self, '_search_error', '') == 'quota_exceeded':
                yield {
                    "type": "info",
                    "message": "⚠️ 百度搜索每日免费额度（100次/天）已用完，以上回答基于 AI 自身知识。"
                }
            else:
                yield {
                    "type": "info",
                    "message": "💡 搜索暂无结果，以上回答基于 AI 自身知识，可能不够准确。"
                }
            self._search_error = ''
            return
        
        # 3. 发送搜索来源信息（带链接）
        sources_info = {
            "type": "search_sources",
            "message": f"🔍 找到 {len(search_results)} 条搜索结果",
            "sources": []
        }
        for i, result in enumerate(search_results, 1):
            sources_info["sources"].append({
                "index": i,
                "title": result.get("title", ""),
                "url": result.get("url", "")
            })
        yield sources_info
        
        # 4. 构建上下文
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
        """执行百度搜索，失败时返回空列表"""
        if self.baidu_api_key:
            return await self._search_baidu(query)
        else:
            logger.warning("百度搜索 API Key 未配置")
            return []
    
    async def _search_baidu(self, query: str) -> List[Dict[str, str]]:
        """
        使用百度搜索 API（千帆平台）
        
        API 文档：https://cloud.baidu.com/doc/WENXINWORKSHOP/s/Hlkz3p71k
        """
        if not self.baidu_api_key:
            logger.warning("百度搜索 API Key 未配置")
            return []
        
        async with httpx.AsyncClient() as client:
            try:
                # 百度千帆搜索 API
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
                
                if response.status_code == 429:
                    logger.warning("百度 API 429：每日免费额度已用完")
                    self._search_error = "quota_exceeded"
                    return []

                if response.status_code != 200:
                    logger.error(f"百度搜索 API 调用失败: {response.status_code} - {response.text}")
                    self._search_error = "api_error"
                    return []
                
                data = response.json()
                results = []
                
                # 解析百度搜索结果
                for ref in data.get("references", [])[:5]:
                    results.append({
                        "title": ref.get("title", ""),
                        "content": ref.get("content", "")[:500],  # 限制内容长度
                        "url": ref.get("url", "")
                    })
                
                logger.info(f"百度搜索完成: '{query[:30]}...', 找到 {len(results)} 条结果")
                return results
                
            except Exception as e:
                logger.error(f"百度搜索失败: {e}")
                return []

    def _build_context(self, results: List[Dict[str, str]]) -> str:
        """
        构建搜索上下文（带标题和链接）
        """
        context_parts = []
        
        for i, result in enumerate(results, 1):
            title = result.get("title", "未知标题")
            url = result.get("url", "")
            content = result.get("content", "")[:300]  # 限制内容长度
            context_parts.append(f"[{i}] {title}\n链接: {url}\n摘要: {content}")
        
        return "\n\n".join(context_parts)


# 全局搜索 Agent 实例
search_agent = SearchAgent()
