"""
LLM 封装模块

负责：
- 封装 DeepSeek/MiMo API 调用
- 支持流式输出
- 统一接口，方便切换模型
"""
from typing import AsyncGenerator, Optional, List, Dict, Any
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

    async def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        支持 Function Calling 的流式对话

        流式返回结构化事件（dict），调用方据此判断是文本内容还是工具调用。

        Args:
            messages: 消息列表（支持 tool role）
            tools: 工具定义列表（OpenAI Function Calling 格式）
            temperature: 温度参数
            max_tokens: 最大 token 数

        Yields:
            Dict: {"type": "content", "content": "文本片段"} 或
                  {"type": "tool_calls", "calls": [{"id":..., "name":..., "args":...}]} 或
                  {"type": "done"}
        """
        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )

            full_content = ""
            tool_calls_acc: Dict[int, Dict[str, Any]] = {}
            final_tool_calls: List[Dict[str, Any]] = []

            async for chunk in stream:
                delta = chunk.choices[0].delta

                # 处理文本内容
                if delta.content:
                    full_content += delta.content
                    yield {"type": "content", "content": delta.content}

                # 处理工具调用增量
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {
                                "id": tc_delta.id or "",
                                "type": tc_delta.type or "function",
                                "function": {
                                    "name": "",
                                    "arguments": ""
                                }
                            }

                        entry = tool_calls_acc[idx]
                        if tc_delta.id:
                            entry["id"] = tc_delta.id
                        if tc_delta.type:
                            entry["type"] = tc_delta.type
                        if tc_delta.function:
                            if tc_delta.function.name:
                                entry["function"]["name"] += tc_delta.function.name
                            if tc_delta.function.arguments:
                                entry["function"]["arguments"] += tc_delta.function.arguments

                # 在流结束时，汇总所有工具调用
                if chunk.choices[0].finish_reason == "tool_calls":
                    for idx in sorted(tool_calls_acc.keys()):
                        call = tool_calls_acc[idx]
                        call["function"]["arguments"] = call["function"]["arguments"].strip()
                        final_tool_calls.append(call)
                    if final_tool_calls:
                        yield {"type": "tool_calls", "calls": final_tool_calls}

            # 流结束
            yield {"type": "done"}

        except Exception as e:
            logger.error(f"LLM Function Calling 失败: {e}")
            raise


# 全局 LLM 客户端实例
llm_client = LLMClient()
