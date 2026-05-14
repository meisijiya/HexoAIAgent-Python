"""
Agent 调度器模块（优化版 v2）

负责：
- 分析用户意图（优化：快速判断优先，减少 LLM 调用）
- 路由到合适的 Agent
- 协调多个 Agent 协作
- 支持 ReAct 模式（思考-行动-观察循环）
- 传递 session_id 给所有 Agent
"""
from typing import AsyncGenerator, Dict, Any, Optional
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

# LLM 意图分析提示词（仅在快速判断无法确定时使用）
INTENT_PROMPT = """你是一个意图分析助手。根据用户的消息，判断应该使用哪个 Agent 来回答。

Agent 类型：
- chat: 普通对话、闲聊、通用知识问题
- knowledge: 关于具体技术文档、项目相关、需要引用资料的问题
- search: 需要最新信息、实时数据、明确要求搜索的问题
- react: 需要多步推理、对比分析、复杂决策的问题

请只返回一个单词：chat、knowledge、search 或 react

用户消息：{message}

判断结果："""


class Orchestrator:
    """
    Agent 调度器（优化版 v2）
    
    优化策略：
    1. 命令优先（/搜索、/知识库、/react）
    2. 快速关键词判断（80% 的情况）
    3. LLM 判断兜底（20% 的情况）
    4. 传递 session_id 给所有 Agent
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
        
        # 调用对应的 Agent（传递 session_id）
        if agent_type == AgentType.KNOWLEDGE:
            async for msg in knowledge_agent.search_and_answer_with_info(message, session_id, stream):
                yield msg
                
        elif agent_type == AgentType.SEARCH:
            async for chunk in search_agent.search_and_answer(message, session_id, stream):
                yield {"type": "content", "content": chunk}
                
        elif agent_type == AgentType.REACT:
            async for msg in react_agent.process(message, session_id, stream):
                yield msg
                
        else:  # CHAT
            async for chunk in chat_agent.chat(message, session_id, stream):
                yield {"type": "content", "content": chunk}
        
        yield {"type": "done", "agent": agent_type, "agent_name": agent_name}
    
    async def _determine_agent(self, message: str, command: str = None) -> AgentType:
        """
        确定使用哪个 Agent（优化版）
        
        优先级：
        1. 明确命令（/搜索、/知识库、/react）
        2. 快速关键词判断
        3. LLM 判断（兜底）
        """
        # 1. 如果有明确命令，直接路由
        if command:
            if command.startswith("/搜索") or command.startswith("/search"):
                return AgentType.SEARCH
            elif command.startswith("/知识库") or command.startswith("/knowledge"):
                return AgentType.KNOWLEDGE
            elif command.startswith("/react") or command.startswith("/推理"):
                return AgentType.REACT
        
        # 2. 快速关键词判断（不调用 LLM）
        quick_result = self._quick_classify(message)
        if quick_result:
            logger.info(f"快速判断: {quick_result}")
            return quick_result
        
        # 3. 使用 LLM 分析意图（兜底）
        logger.info("快速判断无法确定，使用 LLM 分析")
        return await self._llm_classify(message)
    
    def _quick_classify(self, message: str) -> Optional[AgentType]:
        """
        快速分类（关键词匹配）
        
        返回 None 表示无法快速判断，需要 LLM 介入
        """
        
        # ========== 搜索请求判断 ==========
        search_patterns = [
            "搜索", "搜一下", "查一下", "查找",
            "最新", "新闻", "今天", "现在", "最近",
            "2024", "2025", "2026"
        ]
        for pattern in search_patterns:
            if pattern in message:
                return AgentType.SEARCH
        
        # ========== ReAct 复杂推理判断 ==========
        react_patterns = [
            "对比", "比较", "分析", "总结", "推荐",
            "方案", "选择", "优缺点", "利弊",
            "哪个更好", "怎么选"
        ]
        for pattern in react_patterns:
            if pattern in message:
                return AgentType.REACT
        
        # ========== 知识库问答判断 ==========
        knowledge_patterns = [
            "怎么", "如何", "为什么", "是什么",
            "教程", "配置", "安装", "部署", "实现",
            "报错", "错误", "失败", "问题", "解决",
            "原理", "机制", "流程", "步骤"
        ]
        for pattern in knowledge_patterns:
            if pattern in message:
                return AgentType.KNOWLEDGE
        
        # ========== 技术栈关键词判断 ==========
        tech_keywords = [
            "Redis", "MySQL", "Docker", "Hexo", "Git",
            "Python", "Java", "JavaScript", "Node.js",
            "Spring", "Django", "Flask", "FastAPI",
            "Nginx", "Linux", "Vue", "React", "Angular",
            "PostgreSQL", "MongoDB", "Elasticsearch",
            "Kafka", "RabbitMQ", "MQTT"
        ]
        for keyword in tech_keywords:
            if keyword.lower() in message.lower():
                return AgentType.KNOWLEDGE
        
        # ========== 闲聊判断 ==========
        chat_patterns = [
            "你好", "谢谢", "再见", "早上好", "晚安",
            "嗯", "好的", "OK", "ok", "是的", "不是",
            "哈哈", "呵呵", "😊", "👍"
        ]
        for pattern in chat_patterns:
            if pattern in message:
                return AgentType.CHAT
        
        # 无法快速判断，返回 None
        return None
    
    async def _llm_classify(self, message: str) -> AgentType:
        """
        使用 LLM 分析意图（兜底方案）
        """
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
            logger.error(f"LLM 意图分析失败: {e}")
            return AgentType.CHAT


# 全局调度器实例
orchestrator = Orchestrator()
