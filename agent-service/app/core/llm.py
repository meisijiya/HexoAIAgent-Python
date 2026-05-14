"""
LLM 封装模块

负责：
- 封装 DeepSeek/MiMo API 调用
- 支持流式输出
- 统一接口，方便切换模型
"""
from typing import AsyncGenerator, Optional, List, Dict
from openai import AsyncOpenAI
from loguru import logger

from app.config import settings


class LLMClient:
    """
    LLM 客户端
    
    封装 OpenAI 兼容 API（DeepSeek/MiMo）
    """
    
    def __init__(self):
        """初始化 LLM 客户端"""
        self.client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_API_URL
        )
        self.model = settings.DEEPSEEK_MODEL
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """
        非流式对话
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大 token 数
        
        Returns:
            str: 回复内容
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            content = response.choices[0].message.content
            logger.debug(f"LLM 回复: {content[:100]}...")
            
            return content
            
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            raise
    
    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> AsyncGenerator[str, None]:
        """
        流式对话
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大 token 数
        
        Yields:
            str: 回复内容片段
        """
        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error(f"LLM 流式调用失败: {e}")
            raise


# 全局 LLM 客户端实例
llm_client = LLMClient()
