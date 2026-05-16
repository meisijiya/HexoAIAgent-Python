"""
ReAct Agent 模块（v3 - Function Calling）

实现 ReAct（Reasoning + Acting）设计模式：
- Function Calling 替代文本解析，消除格式脆弱性
- 思考链全程流式可见
- 最多 3 次搜索，智能决定是否调用工具
"""
import json
import os
from typing import AsyncGenerator, Dict, Any, List
from loguru import logger

from app.core.llm import llm_client
from app.core.history_manager import history_manager
from app.agents.tools import tool_collection


MAX_ITERATIONS = int(os.getenv("REACT_MAX_ITERATIONS", "5"))


REACT_SYSTEM_PROMPT = """你是一个善于推理分析的智能助手，名叫"老江湖"。你的任务是深入分析用户问题，并在需要时使用工具搜集信息。

## 工作流程
1. 先思考：分析问题的关键维度，制定回答框架
2. 评估：如果已有足够知识回答 → 直接给出全面分析
3. 如果缺少关键信息 → 调用工具搜索，获得信息后继续分析

## 重要规则
- 先展示思考链（列出你要从哪几个维度分析），再决定是否搜索
- 最多搜索 2-3 次，收集到关键信息后立即给出最终答案
- 不要重复搜索相同的内容
- 最终答案要结构清晰、有深度，基于思考框架和搜索结果组织

## 工具使用原则
- 只在确实需要外部信息时才调用工具
- 如果问题属于常识或你已有充分知识，直接回答即可
- 对比分析、多因素评估类问题优先调用工具获取多方信息"""


class ReActAgent:
    """ReAct Agent（v3 - Function Calling）"""

    def __init__(self):
        self.max_iterations = MAX_ITERATIONS
        self.max_search_count = 3

    async def process(
        self,
        query: str,
        session_id: str = None,
        stream: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理用户查询（Function Calling 驱动）

        Args:
            query: 用户查询
            session_id: 会话 ID
            stream: 是否流式输出

        Yields:
            Dict: 包含思考过程、工具调用和最终答案的事件
        """

        yield {"type": "routing", "agent": "react", "message": "正在深度推理分析..."}

        logger.info(f"ReAct Agent (v3) 开始处理: {query[:50]}...")

        # 1. 获取对话历史
        history = ""
        if session_id:
            history = await history_manager.get_history(session_id)

        history_section = ""
        if history:
            history_section = f"\n\n## 对话历史（辅助理解上下文）\n{history}"

        # 2. 构建消息
        tools_schema = tool_collection.get_tools_schema()
        system_content = REACT_SYSTEM_PROMPT + history_section

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": query}
        ]

        # 3. ReAct 循环（Function Calling）
        search_count = 0
        all_thoughts = []
        tool_events = []

        for iteration in range(self.max_iterations):
            logger.info(
                f"ReAct 循环 {iteration + 1}/{self.max_iterations}，搜索: {search_count}"
            )

            # 搜索次数达上限 → 强制收束
            if search_count >= self.max_search_count:
                messages.append({
                    "role": "user",
                    "content": "已搜索足够多的信息。请基于已有信息直接给出最终分析和结论，不要调用工具。"
                })

            # 调用 LLM（Function Calling 流式）—— 实时流式输出内容
            response_text = ""
            tool_calls = []

            async for event in llm_client.chat_with_tools(
                messages=messages,
                tools=tools_schema,
                temperature=0.3,
                max_tokens=2000
            ):
                if event["type"] == "content":
                    chunk = event["content"]
                    response_text += chunk
                    yield {"type": "content", "content": chunk}
                elif event["type"] == "tool_calls":
                    tool_calls = event["calls"]

            # 有工具调用 → 追加 assistant 消息，执行工具后继续循环
            if tool_calls and search_count < self.max_search_count:
                all_thoughts.append(response_text)

                # 追加助手消息（含 tool_calls）
                assistant_msg = {"role": "assistant", "content": response_text or None}
                assistant_msg["tool_calls"] = tool_calls
                messages.append(assistant_msg)

                for tc in tool_calls:
                    func_name = tc["function"]["name"]
                    func_args_str = tc["function"]["arguments"]

                    try:
                        func_args = json.loads(func_args_str)
                    except json.JSONDecodeError:
                        func_args = {"query": func_args_str}

                    yield {
                        "type": "react_action",
                        "content": f"调用工具: {func_name}",
                        "tool": func_name,
                        "input": func_args
                    }

                    # 执行工具
                    observation = await tool_collection.call(func_name, func_args)

                    if func_name in ("web_search", "knowledge_search"):
                        search_count += 1

                    # 处理搜索结果
                    if isinstance(observation, dict) and func_name == "web_search":
                        obs_summary = observation.get("summary", "")
                        sources = observation.get("sources", [])
                        is_error = observation.get("error", "")

                        if sources:
                            tool_events.append({
                                "action": func_name,
                                "sources": sources
                            })
                        elif is_error or "⚠️" in obs_summary:
                            # 搜索工具不可用，前端显示友好提示
                            yield {
                                "type": "info",
                                "message": obs_summary
                            }

                        obs_text = obs_summary
                    else:
                        obs_text = str(observation)
                        if len(obs_text) > 500:
                            obs_text = obs_text[:500] + "..."

                    yield {
                        "type": "react_observation",
                        "content": obs_text
                    }

                    # 追加工具结果到消息
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": str(observation)
                    })

                continue  # 继续下一轮循环

            # 无工具调用 → 最终答案已实时流式输出，只需补元数据
            logger.info(
                f"ReAct Agent 完成，迭代: {iteration + 1}，搜索: {search_count}"
            )

            yield {
                "type": "react_formatted",
                "thought": "",
                "tools": tool_events
            }
            break

        else:
            # 达到最大循环次数
            logger.warning(f"ReAct Agent 达到最大迭代: {self.max_iterations}")
            fallback = "抱歉，我无法在有限步骤内回答这个问题。请换一种方式提问。"
            for i in range(0, len(fallback), 6):
                yield {"type": "content", "content": fallback[i:i + 6]}
            yield {
                "type": "react_formatted",
                "thought": "",
                "tools": tool_events
            }


# 全局 ReAct Agent 实例
react_agent = ReActAgent()
