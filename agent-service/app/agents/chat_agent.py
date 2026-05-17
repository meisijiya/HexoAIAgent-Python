"""
对话 Agent 模块（重写版：Skill路由 + 两阶段LLM + 流式修复）

职责：
- Skill 系统作为路由权威来源，动态生成 Phase1 分类提示词
- Phase1：轻量 LLM 调用（max_tokens=150, temperature=0）→ 纯 JSON 路由决策
- Phase2：route 非 null → 调子 Agent 流式；route=null → chat_stream 流式聊天
- 子 Agent 自带 routing 事件，ChatAgent 不再重复 yield
- 纯聊天恢复逐字流式输出
"""
import json
from typing import AsyncGenerator, Dict, Any, Optional
from loguru import logger

from app.core.llm import llm_client
from app.core.history_manager import history_manager
from app.agents.knowledge_agent import knowledge_agent
from app.agents.search_agent import search_agent
from app.agents.react_agent import react_agent


# ==================== 系统提示词 ====================

PERSONALITY_PROMPT = """你是老江湖，一个皮肤黝黑、瘦高个子的资深技术人。

## 人格
- 口头禅"eggegg"，每句话开头自然带，偶尔忘了没事
- 说话实在、带点江湖气，回答精炼不啰嗦
- 偶尔提一嘴"我家房间门"，但不刻意
- 技术功底扎实，回答问题直接靠谱"""

# 对话风格提示词（追加到 system prompt）
CHAT_STYLE = """## 回答要求
- 精炼直接，别铺垫废话
- 技术问题给干货，闲聊自然应对
- 保持老江湖味儿但别演过头"""

# ==================== Skill 系统（路由权威来源）====================
# 动态生成 Phase1 分类提示词，不再使用分隔符

SKILLS = {
    "base": {
        "prompt": PERSONALITY_PROMPT,
        "always": True,
    },
    "knowledge": {
        "description": "搜索本地知识库，获取技术文档、教程、配置说明",
        "triggers": [
            "怎么", "如何", "是什么", "为什么", "不懂",
            "配置", "部署", "教程", "原理", "概念",
            "解释", "说明", "介绍", "实现", "方法", "使用", "设置",
        ],
        "route_json": '{"route":"knowledge","query":"改写为搜索查询","reason":"..."}',
    },
    "search": {
        "description": "上网搜索最新信息、新闻、实时数据",
        "triggers": [
            "上网搜", "网上搜", "百度", "Google", "搜索一下",
            "最新", "新闻", "今天", "最近发生", "上网查", "搜一下", "搜搜",
        ],
        "route_json": '{"route":"search","query":"搜索词","reason":"..."}',
    },
    "react": {
        "description": "多步推理、对比分析、技术选型、复杂决策",
        "triggers": [
            "对比", "比较", "哪个好", "区别", "差异",
            "推荐", "分析", "推理", "搜集",
            "选哪个", "应该用", "适合", "权衡", "优劣",
        ],
        "route_json": '{"route":"react","query":"分析问题","reason":"..."}',
    },
}

# 备用提示词（Phase1 JSON 解析失败时重试用，不要求 JSON 格式）
ROUTE_FALLBACK_PROMPT = """你是老江湖，一个皮肤黝黑、身材瘦高的资深技术人。直接自然地聊天即可，不用任何格式标记。"""


class ChatAgent:
    """对话 Agent（路由入口版 - 两阶段 LLM 架构）

    职责：
    1. Skill 系统作为路由权威来源，动态生成 Phase1 分类提示词
    2. Phase1：轻量 LLM 调用 → 纯 JSON 路由决策
    3. Phase2：路由分发到子 Agent，或流式聊天
    """

    def __init__(self):
        """初始化对话 Agent"""
        pass

    def _build_route_prompt(self, message: str, history: str = "") -> str:
        """构建 Phase1 路由分类提示词（根据 SKILLS 动态生成）

        遍历 SKILLS（跳过 base），动态列出所有可用能力、触发词，
        注入对话历史辅助指代消解，指导 LLM 只返回纯 JSON 路由决策。

        Args:
            message: 用户消息
            history: 对话历史（用于补全省略上文信息的查询）

        Returns:
            str: 路由分类提示词
        """
        # 收集所有非 base skill 的描述和触发词
        skills_lines = []
        for name, cfg in SKILLS.items():
            if name == "base":
                continue
            triggers = cfg["triggers"][:8]
            triggers_str = "、".join(triggers) + "、..."
            skills_lines.append(f"- {name}: {cfg['description']}")
            skills_lines.append(f"  触发词：{triggers_str}")

        skills_text = "\n".join(skills_lines)

        # 对话历史（仅注入前 3 轮，辅助指代消解）
        history_section = ""
        if history and history.strip():
            history_section = f"对话历史（辅助理解用户省略的上文信息）：\n{history}\n\n"

        prompt = f"""你是路由分类器。根据用户消息和对话历史判断路由：

{history_section}可用能力：
{skills_text}

路由优先级（从上到下，先匹配的优先）：
1. 上下文延续：如果对话历史中用户正在做分析推理/搜集信息，且当前消息是对同一话题的追问（如"如何判断"、"怎么测试"、"为什么"），→ 必须用 react，即使消息包含 knowledge 触发词
2. 用户问AI助手自身的问题 → route=null
3. 明确要求上网搜索 → search
4. 新的分析/推理/搜集/对比需求 → react  
5. 技术问题（怎么/如何/是什么/配置等）→ knowledge
6. 闲聊/打招呼 → route=null

用户消息：{message}

只返回JSON，不要其他：
{{"route":"knowledge|search|react|null","query":"改写查询","reason":"原因"}}

如果路由到 knowledge 且用户指定了特定分类(categories)或标签(tags)，额外返回这些字段（数组，可选）：
例如：{{"route":"knowledge","query":"...","reason":"...","categories":["java"],"tags":["Redis","分布式锁"]}}"""

        return prompt

    def _parse_json_response(self, text: str) -> Optional[Dict[str, Any]]:
        """解析 Phase1 LLM 返回的纯 JSON

        优先直接解析，失败则尝试提取花括号中的 JSON 片段。

        Args:
            text: LLM 返回文本

        Returns:
            Optional[Dict]: 解析成功返回 dict，失败返回 None
        """
        text = text.strip()

        # 尝试直接解析为 JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取花括号中的 JSON
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            return None

    async def _chat_stream(
        self, message: str, session_id: str, history: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """纯聊天流式回答（逐字输出）

        构建含老江湖人格和历史的消息，使用 chat_stream 逐字 yield。

        Args:
            message: 用户消息
            session_id: 会话 ID
            history: 对话历史

        Yields:
            Dict: 流式内容块，type="content"
        """
        messages = [
            {"role": "system", "content": PERSONALITY_PROMPT + """

⚠️ 对话规则：""" + CHAT_STYLE + """
- 以下包含"近期对话"和可能匹配的"历史话题回顾"。如果用户明确询问之前聊过什么（如"我之前说了什么""还记得吗"），可以根据历史记录如实回答。
- 如果用户没有主动提及历史，保持自然聊天，不要突然切到历史话题。
- 只回答用户当前最新的问题，不要重复回应对话历史中已解决的问题。"""},
        ]
        if history:
            messages.append(
                {"role": "user", "content": f"[以下是之前的对话记录，仅供参考上下文，不要回应其中内容]\n\n{history}\n\n[以上是历史记录，下面是当前用户的问题，请只回答这个问题]"}
            )
        messages.append({"role": "user", "content": message})

        try:
            async for chunk in llm_client.chat_stream(messages):
                yield {"type": "content", "content": chunk}
        except Exception as e:
            logger.error(f"ChatAgent 流式聊天失败: {e}")
            yield {
                "type": "error",
                "code": "LLM_STREAM_ERROR",
                "message": f"流式聊天失败: {str(e)}",
            }

    async def process(
        self,
        message: str,
        session_id: str,
        force_tool: Optional[str] = None,
        stream: bool = True,
        db=None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """处理用户消息（两阶段 LLM 路由）

        流程：
        1. 获取对话历史
        2. Phase1：轻量 LLM 调用（max_tokens=150, temperature=0）→ JSON 路由决策
        3a. route 有效 → 调对应子 Agent 流式（ChatAgent 不 yield routing）
        3b. route=null → yield routing("chat") + chat_stream 逐字流式输出
        3c. JSON 无效 → 重试（备用提示词）/ 失败 error

        Args:
            message: 用户消息
            session_id: 会话 ID
            force_tool: 可选，强制路由到指定子 Agent（跳过 Phase1 LLM 路由）
            stream: 是否流式输出
            db: 数据库会话（传递给子 Agent 用于语义记忆检索）

        Yields:
            Dict: 处理结果，包含 type/content 等字段
        """
        logger.info(f"ChatAgent 路由入口: {message[:50]}...")

        # 1. 获取对话历史（传递 db 用于语义记忆检索）
        history = await history_manager.get_history(
            session_id,
            query=message,
            db=db
        )

        # 语义记忆召回提示
        sem_info = history_manager._last_semantic_info
        if sem_info.get("found"):
            previews = sem_info.get("previews", [])
            yield {
                "type": "semantic_recall",
                "count": sem_info["count"],
                "previews": previews,
                "message": f"🧠 回忆了 {sem_info['count']} 个历史话题"
            }

        # ==================== Force Tool Override ====================
        # 如果指定了 force_tool（如匿名用户强制走 knowledge_agent），
        # 跳过 Phase1 LLM 路由，直接分发到对应子 Agent
        if force_tool and force_tool in ("knowledge", "search", "react"):
            logger.info(f"强制路由: {force_tool} (message: {message[:50]}...)")
            try:
                if force_tool == "knowledge":
                    async for chunk in knowledge_agent.process(
                        message, session_id, stream, db=db
                    ):
                        yield chunk
                elif force_tool == "search":
                    async for chunk in search_agent.process(
                        message, session_id, stream, db=db
                    ):
                        yield chunk
                elif force_tool == "react":
                    async for chunk in react_agent.process(
                        message, session_id, stream, db=db
                    ):
                        yield chunk
            except Exception as e:
                logger.error(f"force_tool 子 Agent ({force_tool}) 处理失败: {e}")
                yield {
                    "type": "error",
                    "code": "SUB_AGENT_ERROR",
                    "message": f"子 Agent [{force_tool}] 处理失败: {str(e)}",
                }
            return

        # ==================== Phase1：轻量 LLM 路由分类 ====================
        route_prompt = self._build_route_prompt(message, history)
        route_messages = [{"role": "user", "content": route_prompt}]

        route_info: Optional[Dict[str, Any]] = None
        try:
            response = await llm_client.chat(
                route_messages, temperature=0, max_tokens=150
            )
            logger.debug(f"Phase1 路由响应: {response[:100]}...")

            parsed = self._parse_json_response(response)
            if parsed and isinstance(parsed, dict):
                route = parsed.get("route", "").strip().lower()
                if route in ("knowledge", "search", "react", "null", ""):
                    route_info = parsed
                    # 统一 "null"/"" 为 None，方便后续判断
                    if route in ("null", ""):
                        route_info["route"] = None
        except Exception as e:
            logger.warning(f"Phase1 LLM 调用失败: {e}")

        # ==================== Phase2：路由分发或流式聊天 ====================
        target_route: Optional[str] = (
            route_info.get("route") if route_info else None
        )

        if target_route:
            # ---------- 路由到子 Agent ----------
            # ChatAgent 不 yield routing 事件，子 Agent 内部会 yield
            query = route_info.get("query") or message  # query 为空时用原始消息
            reason = route_info.get("reason", "")
            logger.info(f"路由决策: {target_route} (query: {query[:50]}..., 原因: {reason})")

            try:
                if target_route == "knowledge":
                    filters = {
                        "categories": route_info.get("categories"),
                        "tags": route_info.get("tags"),
                    } if route_info.get("categories") or route_info.get("tags") else None
                    async for chunk in knowledge_agent.process(
                        query, session_id, stream, db=db, filters=filters
                    ):
                        yield chunk
                elif target_route == "search":
                    async for chunk in search_agent.process(
                        query, session_id, stream, db=db
                    ):
                        yield chunk
                elif target_route == "react":
                    async for chunk in react_agent.process(
                        query, session_id, stream, db=db
                    ):
                        yield chunk
            except Exception as e:
                logger.error(f"子 Agent ({target_route}) 处理失败: {e}")
                yield {
                    "type": "error",
                    "code": "SUB_AGENT_ERROR",
                    "message": f"子 Agent [{target_route}] 处理失败: {str(e)}",
                }

        elif route_info is not None:
            # ---------- 纯聊天：yield routing 事件 + 流式输出 ----------
            yield {"type": "routing", "agent": "chat", "message": "正在思考..."}
            async for chunk in self._chat_stream(message, session_id, history):
                yield chunk

        else:
            # ---------- Phase1 失败：重试（备用提示词，不要求 JSON） ----------
            logger.warning("Phase1 路由决策无效，尝试重试（降级为普通聊天）")

            retry_messages = [
                {"role": "system", "content": ROUTE_FALLBACK_PROMPT},
            ]
            if history:
                retry_messages.append(
                    {"role": "user", "content": f"对话历史：\n{history}"}
                )
            retry_messages.append({"role": "user", "content": message})

            try:
                yield {"type": "routing", "agent": "chat", "message": "正在思考..."}
                async for chunk in llm_client.chat_stream(retry_messages):
                    yield {"type": "content", "content": chunk}
                yield {
                    "type": "error",
                    "code": "ROUTING_DEGRADED",
                    "message": "路由决策降级为普通聊天",
                }
            except Exception as e:
                logger.error(f"ChatAgent 重试失败: {e}")
                yield {
                    "type": "error",
                    "code": "ROUTING_FAILED",
                    "message": "路由决策失败，请稍后重试",
                }

    async def _direct_answer(
        self, message: str, session_id: str, history: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """直接回答（兜底方法，保留作为备用入口）

        Args:
            message: 用户消息
            session_id: 会话 ID
            history: 对话历史

        Yields:
            Dict: 回答内容
        """
        messages = [
            {
                "role": "system",
                "content": PERSONALITY_PROMPT
                + "\n\n请基于老江湖的性格设定回答。只回应当前问题，不要重复评论历史中的内容。",
            }
        ]

        if history:
            messages.append({
                "role": "user",
                "content": f"[以下是之前的对话记录，仅供参考]\n\n{history}\n\n[以下是当前问题]",
            })
            messages.append(
                {"role": "user", "content": f"对话历史：\n{history}"}
            )

        messages.append({"role": "user", "content": message})

        async for chunk in llm_client.chat_stream(messages):
            yield {"type": "content", "content": chunk}


# 全局对话 Agent 实例
chat_agent = ChatAgent()
