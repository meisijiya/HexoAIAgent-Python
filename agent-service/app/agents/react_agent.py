"""
ReAct Agent 模块（优化版）

实现 ReAct（Reasoning + Acting）设计模式：
- 思考（Reasoning）：分析问题，制定计划
- 行动（Acting）：调用工具获取信息
- 观察（Observing）：查看工具返回结果
- 循环直到得到最终答案

改进点：
- 集成对话历史管理
- 支持上下文理解
"""
import json
from typing import AsyncGenerator, Dict, Any, List
from loguru import logger

from app.core.llm import llm_client
from app.core.history_manager import history_manager
from app.agents.tools import tool_collection


# ReAct Prompt
REACT_PROMPT = """你是一个智能助手，可以使用工具来回答问题。

{tools_description}

{history_section}

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
5. Final Answer 应该简洁明了，直接回答用户问题

用户问题：{query}

请开始回答："""


class ReActAgent:
    """
    ReAct Agent（优化版）
    
    改进点：
    1. 集成对话历史管理
    2. 支持上下文理解
    3. 优化工具调用逻辑
    """
    
    def __init__(self):
        self.max_iterations = 5
    
    async def process(
        self,
        query: str,
        session_id: str = None,
        stream: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理用户查询
        
        Args:
            query: 用户查询
            session_id: 会话 ID（用于获取历史）
            stream: 是否流式输出
        
        Yields:
            Dict: 包含思考过程和最终答案
        """
        
        logger.info(f"ReAct Agent 开始处理: {query[:50]}...")
        
        # 1. 获取对话历史
        history = ""
        if session_id:
            history = await history_manager.get_history(session_id)
        
        # 2. 构建 Prompt
        tools_description = tool_collection.get_tools_description()
        
        history_section = ""
        if history:
            history_section = f"## 对话历史\n{history}\n"
        
        prompt = REACT_PROMPT.format(
            tools_description=tools_description,
            history_section=history_section,
            query=query
        )
        
        messages = [{"role": "user", "content": prompt}]
        
        # 3. ReAct 循环
        full_response = ""
        
        for iteration in range(self.max_iterations):
            logger.info(f"ReAct 循环 {iteration + 1}/{self.max_iterations}")
            
            # 调用 LLM
            response = await llm_client.chat(messages, temperature=0.1)
            
            # 解析响应
            thought, action, action_input, final_answer = self._parse_response(response)
            
            # 发送思考过程
            if thought:
                yield {
                    "type": "react_thought",
                    "content": thought,
                    "iteration": iteration + 1
                }
            
            # 如果有最终答案，结束循环
            if final_answer:
                logger.info(f"ReAct Agent 完成，迭代次数: {iteration + 1}")
                full_response = final_answer
                yield {
                    "type": "content",
                    "content": final_answer
                }
                break
            
            # 如果需要调用工具
            if action:
                yield {
                    "type": "react_action",
                    "content": f"调用工具: {action}",
                    "tool": action,
                    "input": action_input
                }
                
                # 执行工具
                observation = await tool_collection.call(action, action_input)
                
                yield {
                    "type": "react_observation",
                    "content": observation[:200] + "..." if len(observation) > 200 else observation
                }
                
                # 将结果添加到消息中，继续循环
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"Observation: {observation}\n\n请继续思考并给出答案。"})
            else:
                # 没有工具调用也没有最终答案
                full_response = response
                yield {
                    "type": "content",
                    "content": response
                }
                break
        else:
            # 达到最大循环次数
            logger.warning(f"ReAct Agent 达到最大循环次数: {self.max_iterations}")
            full_response = "抱歉，我无法在有限步骤内回答这个问题。请尝试更具体的描述。"
            yield {
                "type": "content",
                "content": full_response
            }
        
        # 4. 保存到历史
        if session_id:
            await history_manager.save_message(session_id, "user", query)
            await history_manager.save_message(session_id, "assistant", full_response)
    
    def _parse_response(self, response: str) -> tuple:
        """
        解析 LLM 响应
        """
        
        thought = None
        action = None
        action_input = {}
        final_answer = None
        
        lines = response.strip().split('\n')
        
        current_section = None
        current_content = []
        
        for line in lines:
            line = line.strip()
            
            if line.startswith("Thought:"):
                if current_section == "action_input" and current_content:
                    try:
                        action_input = json.loads("\n".join(current_content))
                    except:
                        action_input = {"query": "\n".join(current_content)}
                
                current_section = "thought"
                current_content = [line[8:].strip()]
                
            elif line.startswith("Action:"):
                current_section = "action"
                action = line[7:].strip()
                
            elif line.startswith("Action Input:"):
                current_section = "action_input"
                current_content = [line[13:].strip()]
                
            elif line.startswith("Observation:"):
                current_section = "observation"
                
            elif line.startswith("Final Answer:"):
                current_section = "final_answer"
                current_content = [line[13:].strip()]
                
            elif current_section:
                current_content.append(line)
        
        # 处理最后一个 section
        if current_section == "thought":
            thought = "\n".join(current_content)
        elif current_section == "action_input" and current_content:
            try:
                action_input = json.loads("\n".join(current_content))
            except:
                action_input = {"query": "\n".join(current_content)}
        elif current_section == "final_answer":
            final_answer = "\n".join(current_content)
        
        return thought, action, action_input, final_answer


# 全局 ReAct Agent 实例
react_agent = ReActAgent()
