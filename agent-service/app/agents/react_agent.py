"""
ReAct Agent 模块（优化版 v2）

实现 ReAct（Reasoning + Acting）设计模式：
- 思考（Reasoning）：分析问题，制定计划
- 行动（Acting）：调用工具获取信息
- 观察（Observing）：查看工具返回结果
- 循环直到得到最终答案

改进点：
- 强化 Prompt，强制工具调用
- 使用 web_search 工具进行网络搜索
- 最大迭代次数可配置
"""
import json
import os
from typing import AsyncGenerator, Dict, Any, List
from loguru import logger

from app.core.llm import llm_client
from app.core.history_manager import history_manager
from app.agents.tools import tool_collection


# 最大迭代次数（从环境变量读取，默认 5）
MAX_ITERATIONS = int(os.getenv("REACT_MAX_ITERATIONS", "5"))


# ReAct Prompt（智能版）
REACT_PROMPT = """你是一个智能助手，可以使用工具来获取信息，但要智能地决定何时使用工具。

可用工具：
{tools_description}

{history_section}

请严格按照以下格式回答问题：

Thought: 分析问题，决定是否需要使用工具
Action: 工具名称（如果需要）
Action Input: 工具参数（JSON 格式）
Observation: 工具返回的结果
...（可以重复，但不要超过 3 次搜索）
Thought: 分析所有信息，准备给出最终答案
Final Answer: 最终答案

重要规则：
1. **智能决策**：如果问题简单或你已有足够知识，直接给出 Final Answer，不需要调用工具
2. **限制搜索**：最多搜索 2-3 次，避免过度搜索
3. **及时回答**：收集到足够信息后，立即给出 Final Answer
4. **简洁高效**：Final Answer 应该基于已有信息，简洁明了
5. **诚实谦虚**：如果无法回答，请诚实地说不知道

用户问题：{query}

请开始回答："""


class ReActAgent:
    """ReAct Agent（智能版）"""
    
    def __init__(self):
        self.max_iterations = MAX_ITERATIONS
        self.max_search_count = 3  # 最大搜索次数限制
    
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
        
        yield {"type": "routing", "agent": "react", "message": "正在深度推理分析..."}
        
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
        search_count = 0  # 搜索次数计数器
        all_thoughts = []   # 累积所有思考过程
        tool_events = []    # 累积工具调用事件 [{action, sources}]
        
        for iteration in range(self.max_iterations):
            logger.info(f"ReAct 循环 {iteration + 1}/{self.max_iterations}，搜索次数: {search_count}")
            
            # 如果搜索次数达到限制，强制要求给出答案
            if search_count >= self.max_search_count:
                messages.append({
                    "role": "user", 
                    "content": "你已经搜索了足够多的信息。请基于已有的信息，直接给出 Final Answer。不要再调用任何工具。"
                })
            
            # 调用 LLM（流式累积）
            response = ""
            fa_stream_stopped = False  # 标记：检测到 "Final Answer:" 后停止输出原始内容，避免与 react_formatted 重复
            async for chunk in llm_client.chat_stream(messages, temperature=0.1):
                response += chunk
                # 一旦检测到 Final Answer，立即停止输出原始 LLM 内容
                # 之后只通过 react_formatted 事件输出答案
                if "Final Answer:" in response and not fa_stream_stopped:
                    fa_stream_stopped = True
                    # 当前 chunk 可能包含 "Final Answer:" 之前的内容，需要提取出来输出
                    if "Final Answer:" in chunk:
                        before_fa, _, _ = chunk.partition("Final Answer:")
                        if before_fa.strip():
                            yield {"type": "react_thought", "content": before_fa}
                    # "Final Answer:" 之后的内容不再作为原始内容输出
                elif not fa_stream_stopped:
                    yield {"type": "react_thought", "content": chunk}
            
            # 解析响应
            thought, action, action_input, final_answer = self._parse_response(response)
            
            # 累积思考过程
            if thought:
                all_thoughts.append(f"思考 {len(all_thoughts) + 1}: {thought}")
            
            # 如果有最终答案，结束循环
            if final_answer:
                logger.info(f"ReAct Agent 完成，迭代次数: {iteration + 1}，搜索次数: {search_count}")
                full_response = final_answer
                yield {
                    "type": "react_formatted",
                    "thought": "\n\n".join(all_thoughts),
                    "answer": final_answer,
                    "tools": tool_events
                }
                break
            
            # 如果需要调用工具
            if action:
                # 检查搜索次数限制
                if action == "web_search" and search_count >= self.max_search_count:
                    logger.warning(f"搜索次数已达上限 ({self.max_search_count})，跳过搜索")
                    messages.append({
                        "role": "user",
                        "content": f"搜索次数已达上限。请基于已有的信息，直接给出 Final Answer。\n\n已有信息：{response}"
                    })
                    continue
                
                yield {
                    "type": "react_action",
                    "content": f"调用工具: {action}",
                    "tool": action,
                    "input": action_input
                }
                
                # 执行工具
                observation = await tool_collection.call(action, action_input)
                
                # 更新搜索次数
                if action == "web_search":
                    search_count += 1
                
                # 处理搜索结果（结构化 dict 用于前端展示链接）
                if isinstance(observation, dict) and action == "web_search":
                    obs_summary = observation.get("summary", "")
                    sources = observation.get("sources", [])
                    
                    # 累积工具事件（用于 react_formatted 前端渲染）
                    if sources:
                        tool_events.append({
                            "action": action,
                            "sources": sources
                        })
                    
                    # 将结果添加到消息中，继续循环
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": f"Observation: {obs_summary}\n\n请继续思考。如果信息足够，请直接给出 Final Answer。"})
                else:
                    obs_content = str(observation)
                    yield {
                        "type": "react_observation",
                        "content": obs_content[:500] + "..." if len(obs_content) > 500 else obs_content
                    }
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": f"Observation: {obs_content}\n\n请继续思考。如果信息足够，请直接给出 Final Answer。"})
            else:
                # 没有工具调用也没有最终答案，强制给出答案
                # 注意：内容已经在流式输出中逐块输出，此处不再重复 yield
                logger.info(f"ReAct Agent 无工具调用，强制给出答案")
                full_response = response
                break
        else:
            # 达到最大循环次数
            logger.warning(f"ReAct Agent 达到最大循环次数: {self.max_iterations}")
            full_response = "抱歉，我无法在有限步骤内回答这个问题。请尝试更具体的描述。"
            yield {
                "type": "react_thought",
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
