"""
对话 Agent 模块

负责：
- 处理用户对话
- 管理对话上下文
- 生成回复
"""
from typing import AsyncGenerator, List, Dict, Optional
from loguru import logger

from app.core.llm import llm_client
from app.core.redis import get_session_context, add_message_to_context


# 系统提示词
SYSTEM_PROMPT = """你是一个友好的 AI 助手，专门帮助用户解答关于 Hexo 博客和相关技术的问题。

你的特点：
1. 友好、耐心、专业
2. 回答简洁明了，避免冗长
3. 如果不确定答案，诚实地说不知道
4. 使用中文回复

请根据用户的问题提供有帮助的回答。"""


class ChatAgent:
    """
    对话 Agent
    
    处理用户对话，支持上下文记忆
    """
    
    def __init__(self):
        """初始化对话 Agent"""
        self.system_prompt = SYSTEM_PROMPT
    
    async def chat(
        self,
        user_message: str,
        session_id: str,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        处理用户对话
        
        Args:
            user_message: 用户消息
            session_id: 会话 ID
            stream: 是否流式输出
        
        Yields:
            str: 回复内容片段
        """
        logger.info(f"收到用户消息: {user_message[:50]}...")
        
        # 获取历史上下文
        context = await get_session_context(session_id)
        
        # 构建消息列表
        messages = self._build_messages(user_message, context)
        
        # 保存用户消息到上下文
        await add_message_to_context(session_id, "user", user_message)
        
        # 调用 LLM 生成回复
        full_response = ""
        
        if stream:
            async for chunk in llm_client.chat_stream(messages):
                full_response += chunk
                yield chunk
        else:
            response = await llm_client.chat(messages)
            full_response = response
            yield response
        
        # 保存助手回复到上下文
        await add_message_to_context(session_id, "assistant", full_response)
        
        logger.info(f"回复完成: {full_response[:50]}...")
    
    def _build_messages(
        self,
        user_message: str,
        context: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """
        构建消息列表
        
        Args:
            user_message: 用户消息
            context: 历史上下文
        
        Returns:
            List[Dict[str, str]]: 消息列表
        """
        messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        
        # 添加历史上下文（最多 10 条）
        for msg in context[-10:]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        # 添加当前用户消息
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        return messages


# 全局对话 Agent 实例
chat_agent = ChatAgent()
