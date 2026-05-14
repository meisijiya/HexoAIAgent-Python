"""
Agent 调度器模块

负责：
- 分析用户意图
- 路由到合适的 Agent
- 协调多个 Agent 协作
"""
from typing import AsyncGenerator, Dict, Any
from enum import Enum
from loguru import logger

from app.agents.chat_agent import chat_agent
from app.agents.knowledge_agent import knowledge_agent
from app.agents.search_agent import search_agent
from app.core.llm import llm_client


class AgentType(str, Enum):
    """Agent 类型枚举"""
    CHAT = "chat"
    KNOWLEDGE = "knowledge"
    SEARCH = "search"


# 意图分析提示词
INTENT_PROMPT = """你是一个意图分析助手。根据用户的消息，判断应该使用哪个 Agent 来回答。

Agent 类型：
- chat: 普通对话、闲聊、通用问题
- knowledge: 关于 Hexo 博客、技术文档、教程相关的问题
- search: 需要最新信息、实时数据、或者明确要求搜索的问题

请只返回一个单词：chat、knowledge 或 search

用户消息：{message}

判断结果："""


class Orchestrator:
    """
    Agent 调度器
    
    根据用户意图路由到合适的 Agent
    """
    
    async def process(
        self,
        message: str,
        session_id: str,
        command: str = None,
        stream: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理用户消息
        
        Args:
            message: 用户消息
            session_id: 会话 ID
            command: 命令（如 /搜索）
            stream: 是否流式输出
        
        Yields:
            Dict: 包含类型和内容的消息
        """
        # 根据命令或意图选择 Agent
        agent_type = await self._determine_agent(message, command)
        
        logger.info(f"路由到 Agent: {agent_type}")
        
        # 发送路由信息
        yield {"type": "routing", "agent": agent_type}
        
        # 调用对应的 Agent
        if agent_type == AgentType.KNOWLEDGE:
            async for chunk in knowledge_agent.search_and_answer(message, stream):
                yield {"type": "content", "content": chunk}
        elif agent_type == AgentType.SEARCH:
            async for chunk in search_agent.search_and_answer(message, stream):
                yield {"type": "content", "content": chunk}
        else:  # CHAT
            async for chunk in chat_agent.chat(message, session_id, stream):
                yield {"type": "content", "content": chunk}
        
        yield {"type": "done", "agent": agent_type}
    
    async def _determine_agent(self, message: str, command: str = None) -> AgentType:
        """
        确定使用哪个 Agent
        
        Args:
            message: 用户消息
            command: 命令
        
        Returns:
            AgentType: Agent 类型
        """
        # 如果有明确命令，直接路由
        if command:
            if command.startswith("/搜索") or command.startswith("/search"):
                return AgentType.SEARCH
            elif command.startswith("/知识库") or command.startswith("/knowledge"):
                return AgentType.KNOWLEDGE
        
        # 使用 LLM 分析意图
        try:
            prompt = INTENT_PROMPT.format(message=message)
            messages = [{"role": "user", "content": prompt}]
            
            response = await llm_client.chat(messages, temperature=0.1, max_tokens=10)
            intent = response.strip().lower()
            
            if "knowledge" in intent:
                return AgentType.KNOWLEDGE
            elif "search" in intent:
                return AgentType.SEARCH
            else:
                return AgentType.CHAT
                
        except Exception as e:
            logger.error(f"意图分析失败: {e}")
            # 默认使用对话 Agent
            return AgentType.CHAT


# 全局调度器实例
orchestrator = Orchestrator()
