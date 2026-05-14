"""
Agent 调度器模块（支持 ReAct）

负责：
- 分析用户意图
- 路由到合适的 Agent
- 协调多个 Agent 协作
- 支持 ReAct 模式（思考-行动-观察循环）
"""
from typing import AsyncGenerator, Dict, Any
from enum import Enum
from loguru import logger

from app.agents.chat_agent import chat_agent
from app.agents.knowledge_agent import knowledge_agent
from app.agents.search_agent import search_agent
from app.agents.react_agent import react_agent
from app.core.llm import llm_client


class AgentType(str, Enum):
    """Agent 类型枚举"""
    CHAT = "chat"
    KNOWLEDGE = "knowledge"
    SEARCH = "search"
    REACT = "react"


# Agent 中文名称映射
AGENT_NAMES = {
    AgentType.CHAT: "对话 Agent",
    AgentType.KNOWLEDGE: "知识库 Agent",
    AgentType.SEARCH: "搜索 Agent",
    AgentType.REACT: "ReAct Agent",
}

# 意图分析提示词
INTENT_PROMPT = """你是一个意图分析助手。根据用户的消息，判断应该使用哪个 Agent 来回答。

Agent 类型：
- chat: 普通对话、闲聊、通用问题
- knowledge: 关于 Hexo 博客、技术文档、教程相关的问题
- search: 需要最新信息、实时数据、或者明确要求搜索的问题
- react: 需要多步推理、工具调用、复杂分析的问题

请只返回一个单词：chat、knowledge、search 或 react

用户消息：{message}

判断结果："""


class Orchestrator:
    """
    Agent 调度器（支持 ReAct）
    
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
        agent_name = AGENT_NAMES.get(agent_type, "未知 Agent")
        
        logger.info(f"路由到 Agent: {agent_name}")
        
        # 发送路由信息
        yield {
            "type": "routing",
            "agent": agent_type,
            "agent_name": agent_name,
            "message": f"🤖 正在调用 {agent_name}..."
        }
        
        # 调用对应的 Agent
        if agent_type == AgentType.KNOWLEDGE:
            async for msg in knowledge_agent.search_and_answer_with_info(message, stream):
                yield msg
                
        elif agent_type == AgentType.SEARCH:
            async for chunk in search_agent.search_and_answer(message, stream):
                yield {"type": "content", "content": chunk}
                
        elif agent_type == AgentType.REACT:
            async for msg in react_agent.process(message, stream):
                yield msg
                
        else:  # CHAT
            async for chunk in chat_agent.chat(message, session_id, stream):
                yield {"type": "content", "content": chunk}
        
        yield {"type": "done", "agent": agent_type, "agent_name": agent_name}
    
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
            elif command.startswith("/react") or command.startswith("/推理"):
                return AgentType.REACT
        
        # 关键词快速判断
        quick_result = self._quick_classify(message)
        if quick_result:
            return quick_result
        
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
            elif "react" in intent:
                return AgentType.REACT
            else:
                return AgentType.CHAT
                
        except Exception as e:
            logger.error(f"意图分析失败: {e}")
            # 默认使用对话 Agent
            return AgentType.CHAT
    
    def _quick_classify(self, message: str) -> AgentType:
        """
        快速分类（关键词）
        """
        # 搜索关键词
        search_keywords = ["搜索", "查找", "最新", "新闻", "今天", "现在"]
        for keyword in search_keywords:
            if keyword in message:
                return AgentType.SEARCH
        
        # 知识库关键词
        knowledge_keywords = ["怎么", "如何", "是什么", "教程", "配置", "安装", "部署"]
        for keyword in knowledge_keywords:
            if keyword in message:
                return AgentType.KNOWLEDGE
        
        # ReAct 关键词（需要多步推理）
        react_keywords = ["对比", "比较", "分析", "总结", "推荐", "方案"]
        for keyword in react_keywords:
            if keyword in message:
                return AgentType.REACT
        
        return None  # 无法快速判断，交给 LLM


# 全局调度器实例
orchestrator = Orchestrator()
