"""
Prompt 构建器模块

负责：
- 结构化 Prompt 构建
- 整合 RAG 召回内容
- 整合对话历史
- 支持模板化配置
"""
from typing import Dict, Any, Optional, List
from loguru import logger


class PromptBuilder:
    """
    结构化 Prompt 构建器
    
    参考博客架构设计：
    - System Prompt：系统提示词
    - RAG Context：RAG 召回内容
    - History：对话历史
    - User Input：用户输入
    """
    
    # 默认模板
    DEFAULT_TEMPLATE = """{system_prompt}

{rag_section}

{history_section}

## 用户问题
{user_input}

请基于以上信息回答用户问题。如果参考资料中没有相关信息，请根据你的知识回答，并注明这不是来自官方文档。"""
    
    # RAG 部分模板
    RAG_TEMPLATE = """## 参考资料
{rag_context}"""
    
    # 对话历史模板
    HISTORY_TEMPLATE = """## 对话历史
{history}"""
    
    def build(
        self,
        system_prompt: str,
        user_input: str,
        rag_context: Optional[str] = None,
        history: Optional[str] = None,
        template: Optional[str] = None
    ) -> str:
        """
        构建结构化 Prompt
        
        Args:
            system_prompt: 系统提示词
            user_input: 用户输入
            rag_context: RAG 召回内容
            history: 对话历史
            template: 自定义模板
        
        Returns:
            str: 构建好的 Prompt
        """
        
        # 构建 RAG 部分
        rag_section = ""
        if rag_context:
            rag_section = self.RAG_TEMPLATE.format(rag_context=rag_context)
        
        # 构建对话历史部分
        history_section = ""
        if history:
            history_section = self.HISTORY_TEMPLATE.format(history=history)
        
        # 使用模板构建
        template = template or self.DEFAULT_TEMPLATE
        
        prompt = template.format(
            system_prompt=system_prompt,
            rag_section=rag_section,
            history_section=history_section,
            user_input=user_input
        )
        
        logger.debug(f"构建 Prompt 完成，长度: {len(prompt)}")
        
        return prompt
    
    def build_messages(
        self,
        system_prompt: str,
        user_input: str,
        rag_context: Optional[str] = None,
        history: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        构建消息列表（用于 Chat API）
        
        Args:
            system_prompt: 系统提示词
            user_input: 用户输入
            rag_context: RAG 召回内容
            history: 对话历史
        
        Returns:
            List[Dict]: 消息列表
        """
        
        messages = []
        
        # 系统提示词
        system_content = system_prompt
        
        if rag_context:
            system_content += f"\n\n## 参考资料\n{rag_context}"
        
        if history:
            system_content += f"\n\n## 对话历史\n{history}"
        
        messages.append({"role": "system", "content": system_content})
        
        # 用户输入
        messages.append({"role": "user", "content": user_input})
        
        return messages


class KnowledgePromptBuilder(PromptBuilder):
    """知识库问答 Prompt 构建器"""
    
    SYSTEM_PROMPT = """你是一个专业的知识库助手，专门根据提供的参考资料回答问题。

你的任务：
1. 仔细阅读参考资料
2. 基于参考资料回答用户问题
3. 如果参考资料中没有相关信息，请根据你的知识回答，并注明这不是来自官方文档
4. 回答要准确、简洁
5. 引用参考资料时注明来源

请用中文回复。"""
    
    def build_for_knowledge(
        self,
        user_input: str,
        rag_context: str,
        history: Optional[str] = None
    ) -> str:
        """构建知识库问答 Prompt"""
        
        return self.build(
            system_prompt=self.SYSTEM_PROMPT,
            user_input=user_input,
            rag_context=rag_context,
            history=history
        )


class ChatPromptBuilder(PromptBuilder):
    """普通对话 Prompt 构建器"""
    
    SYSTEM_PROMPT = """你是一个友好的 AI 助手，专门帮助用户解答关于 Hexo 博客和相关技术的问题。

你的特点：
1. 友好、耐心、专业
2. 回答简洁明了，避免冗长
3. 如果不确定答案，诚实地说不知道
4. 使用中文回复

请根据用户的问题提供有帮助的回答。"""
    
    def build_for_chat(
        self,
        user_input: str,
        history: Optional[str] = None
    ) -> str:
        """构建普通对话 Prompt"""
        
        return self.build(
            system_prompt=self.SYSTEM_PROMPT,
            user_input=user_input,
            history=history
        )


class ReActPromptBuilder(PromptBuilder):
    """ReAct 模式 Prompt 构建器"""
    
    SYSTEM_PROMPT = """你是一个智能助手，可以使用工具来回答问题。

{tools_description}

请严格按照以下格式回答问题：

Thought: 分析问题，思考需要使用什么工具
Action: 工具名称
Action Input: 工具参数（JSON 格式）
Observation: 工具返回的结果
...（可以重复多次 Action/Action Input/Observation）
Thought: 分析所有信息，准备给出最终答案
Final Answer: 最终答案

重要规则：
1. 每次只能调用一个工具
2. 工具参数必须是有效的 JSON 格式
3. 如果不需要工具，可以直接给出 Final Answer
4. 如果无法回答，请诚实地说不知道
5. Final Answer 应该简洁明了，直接回答用户问题"""
    
    def build_for_react(
        self,
        user_input: str,
        tools_description: str,
        rag_context: Optional[str] = None,
        history: Optional[str] = None
    ) -> str:
        """构建 ReAct Prompt"""
        
        system_prompt = self.SYSTEM_PROMPT.format(
            tools_description=tools_description
        )
        
        return self.build(
            system_prompt=system_prompt,
            user_input=user_input,
            rag_context=rag_context,
            history=history
        )


# 全局实例
prompt_builder = PromptBuilder()
knowledge_prompt_builder = KnowledgePromptBuilder()
chat_prompt_builder = ChatPromptBuilder()
react_prompt_builder = ReActPromptBuilder()
