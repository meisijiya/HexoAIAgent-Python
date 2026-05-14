"""
对话 Agent 模块（优化版）

负责：
- 处理用户对话
- 管理对话上下文
- 生成回复
- 集成对话历史管理
"""
from typing import AsyncGenerator, List, Dict, Optional
from loguru import logger

from app.core.llm import llm_client
from app.core.history_manager import history_manager
from app.core.prompt_builder import chat_prompt_builder


# 系统提示词
SYSTEM_PROMPT = """你是一个友好的 AI 助手，专门帮助用户解答关于 Hexo 博客和相关技术的问题。

你的特点：
1. 友好、耐心、专业
2. 回答简洁明了，避免冗长
3. 如果不确定答案，诚实地说不知道
4. 使用中文回复
5. 记住之前的对话内容，保持连贯性

请根据用户的问题提供有帮助的回答。"""


class ChatAgent:
    """
    对话 Agent（优化版）
    
    改进点：
    1. 集成对话历史管理
    2. 使用结构化 Prompt 构建
    3. 支持多轮对话上下文
    """
    
    async def chat(
        self,
        message: str,
        session_id: str,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        处理用户对话
        
        Args:
            message: 用户消息
            session_id: 会话 ID
            stream: 是否流式输出
        
        Yields:
            str: 回复内容片段
        """
        logger.info(f"对话 Agent 处理: {message[:50]}...")
        
        # 1. 获取对话历史
        history = await history_manager.get_history(session_id)
        
        # 2. 构建带历史的消息
        messages = self._build_messages(message, history)
        
        # 3. 调用 LLM 生成回复
        full_response = ""
        
        if stream:
            async for chunk in llm_client.chat_stream(messages):
                full_response += chunk
                yield chunk
        else:
            response = await llm_client.chat(messages)
            full_response = response
            yield response
        
        # 4. 保存到历史
        await history_manager.save_message(session_id, "user", message)
        await history_manager.save_message(session_id, "assistant", full_response)
        
        logger.info(f"对话 Agent 回复完成: {full_response[:50]}...")
    
    def _build_messages(self, message: str, history: str) -> List[Dict[str, str]]:
        """
        构建消息列表（带历史）
        
        Args:
            message: 用户消息
            history: 对话历史
        
        Returns:
            List[Dict]: 消息列表
        """
        messages = []
        
        # 系统提示词（包含历史）
        system_content = SYSTEM_PROMPT
        if history:
            system_content += f"\n\n## 对话历史\n{history}"
        
        messages.append({"role": "system", "content": system_content})
        
        # 用户消息
        messages.append({"role": "user", "content": message})
        
        return messages


# 全局对话 Agent 实例
chat_agent = ChatAgent()
