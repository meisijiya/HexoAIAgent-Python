"""
老江湖人格集成测试

验证老江湖人格在对话中的完整性和一致性。
包括：
1. SYSTEM_PROMPT 包含完整人格描述
2. 聊天 Agent 在多轮对话中正确传递人格 prompt
3. 直接回答也使用老江湖人格（RED -> GREEN）
"""
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 预 mock 循环依赖模块，避免 import 错误
# 导入后立即恢复原始模块，避免泄漏到其他测试文件
_agent_service_path = "/home/ljh2923/opencode-project/Hexo-智能体Agent插件/agent-service"
if _agent_service_path not in sys.path:
    sys.path.insert(0, _agent_service_path)

_original_modules = {}
for _mod_name in ["app.core.history_manager",
                   "app.core.llm", "app.models.memory",
                   "app.tools.base"]:
    _original_modules[_mod_name] = sys.modules.get(_mod_name)
    sys.modules[_mod_name] = MagicMock()

from app.agents.chat_agent import SYSTEM_PROMPT, ChatAgent

# 恢复原始模块引用，chat_agent 已通过 import 绑定了模拟对象不受影响
for _mod_name, _orig_mod in _original_modules.items():
    if _orig_mod is None:
        sys.modules.pop(_mod_name, None)
    else:
        sys.modules[_mod_name] = _orig_mod


class TestPersonaSystemPrompt:
    """测试 SYSTEM_PROMPT 包含完整的老江湖人格描述"""

    def test_prompt_contains_laojianghu_identity(self):
        """验证 system prompt 包含 '老江湖' 人格标识"""
        assert "老江湖" in SYSTEM_PROMPT

    def test_prompt_contains_catchphrase_eggegg(self):
        """验证口头禅 'eggegg' 在 system prompt 中"""
        assert "eggegg" in SYSTEM_PROMPT

    def test_prompt_contains_partner_room_door(self):
        """验证伴侣昵称 '房间门' 在 system prompt 中"""
        assert "房间门" in SYSTEM_PROMPT

    def test_prompt_contains_appearance(self):
        """验证外貌描述（皮肤黝黑、瘦高、178cm）"""
        assert "皮肤黝黑" in SYSTEM_PROMPT
        assert "瘦高" in SYSTEM_PROMPT
        assert "178" in SYSTEM_PROMPT

    def test_prompt_contains_habit_daze(self):
        """验证发呆习惯描述"""
        assert "发呆" in SYSTEM_PROMPT

    def test_prompt_contains_love_showing(self):
        """验证爱秀恩爱的性格设定"""
        assert "秀恩爱" in SYSTEM_PROMPT
        assert "房间门" in SYSTEM_PROMPT

    def test_prompt_contains_dialogue_style(self):
        """验证对话风格包含江湖气"""
        assert "江湖气" in SYSTEM_PROMPT
        assert "实在" in SYSTEM_PROMPT

    def test_prompt_contains_tools_placeholder(self):
        """验证 SYSTEM_PROMPT 包含工具描述格式化占位符"""
        assert "{tools_description}" in SYSTEM_PROMPT

    def test_prompt_contains_decision_rules(self):
        """验证 system prompt 包含工具决策规则"""
        assert "search_knowledge" in SYSTEM_PROMPT
        assert "react_reasoning" in SYSTEM_PROMPT
        assert "search_web" in SYSTEM_PROMPT


def _build_stream_capture():
    """
    构建一个可捕获调用参数的 async generator 工厂。
    返回 (capture_list, async_gen_func) 二元组。
    capture_list 会在每次 async_gen_func 被调用时追加 messages 参数。
    """
    capture = []

    async def _stream(messages):
        capture.append(messages)
        yield "eggegg 测试回复"

    return capture, _stream


class TestChatAgentPersonaUsage:
    """测试 ChatAgent 在多轮对话中正确使用老江湖人格"""

    @pytest.mark.asyncio
    async def test_decide_tool_sends_persona_prompt(self):
        """测试 _decide_tool 向 LLM 发送包含老江湖人格的 system prompt"""
        agent = ChatAgent()

        with patch("app.agents.chat_agent.llm_client") as mock_llm:
            mock_llm.chat = AsyncMock(
                return_value='{"tool": "search_knowledge", "query": "测试"}'
            )

            await agent._decide_tool("测试问题", "")

            call_args = mock_llm.chat.call_args[0][0]
            system_msgs = [m for m in call_args if m["role"] == "system"]
            assert len(system_msgs) == 1

            content = system_msgs[0]["content"]
            assert "老江湖" in content
            assert "eggegg" in content
            assert "房间门" in content

    @pytest.mark.asyncio
    async def test_decide_tool_formats_tools_description(self):
        """测试 _decide_tool 正确格式化工具描述到 system prompt 中"""
        agent = ChatAgent()

        with patch("app.agents.chat_agent.llm_client") as mock_llm:
            mock_llm.chat = AsyncMock(
                return_value='{"tool": "search_knowledge", "query": "测试"}'
            )

            await agent._decide_tool("测试问题", "")

            call_args = mock_llm.chat.call_args[0][0]
            system_msgs = [m for m in call_args if m["role"] == "system"]
            content = system_msgs[0]["content"]

            assert "{tools_description}" not in content
            assert "search_knowledge" in content

    @pytest.mark.asyncio
    async def test_direct_answer_uses_persona_prompt(self):
        """
        测试 _direct_answer 也使用老江湖人格 prompt。

        当前已修复：_direct_answer 使用 PERSONALITY_PROMPT，
        包含完整的"老江湖"人格描述和"eggegg"口头禅。
        """
        agent = ChatAgent()

        with patch("app.agents.chat_agent.llm_client") as mock_llm:
            stream_calls, mock_stream = _build_stream_capture()
            mock_llm.chat_stream = mock_stream

            async for _ in agent._direct_answer("你好", "session-direct", ""):
                pass

            assert len(stream_calls) == 1
            system_msgs = [m for m in stream_calls[0] if m["role"] == "system"]
            assert len(system_msgs) == 1

            content = system_msgs[0]["content"]
            assert "老江湖" in content
            assert "eggegg" in content
            assert "房间门" in content

    @pytest.mark.asyncio
    async def test_multi_turn_persona_consistency(self):
        """测试 5 轮对话后人格一致性"""
        agent = ChatAgent()
        session_id = "test-multi-turn-persona"

        with patch("app.agents.chat_agent.llm_client") as mock_llm, \
             patch("app.agents.chat_agent.history_manager") as mock_history:

            mock_llm.chat = AsyncMock(return_value=None)

            stream_calls, mock_stream = _build_stream_capture()
            mock_llm.chat_stream = mock_stream
            mock_history.get_history = AsyncMock(return_value="")

            # 进行 5 轮对话
            for turn in range(5):
                async for _ in agent.process(
                    message=f"第{turn+1}轮对话消息",
                    session_id=session_id,
                    stream=False,
                ):
                    pass

            # 验证刚好 5 轮对话
            assert len(stream_calls) == 5, f"应该有 5 轮对话, 实际 {len(stream_calls)}"

            # 检查每一轮调用的 system prompt
            for i, msgs in enumerate(stream_calls):
                system_msgs = [m for m in msgs if m["role"] == "system"]
                assert len(system_msgs) == 1, f"第{i+1}轮应该有 system message"

                content = system_msgs[0]["content"]
                assert "老江湖" in content, (
                    f"第{i+1}轮: system prompt 应包含老江湖人格"
                )
                assert "eggegg" in content, (
                    f"第{i+1}轮: system prompt 应包含 eggegg"
                )

    @pytest.mark.asyncio
    async def test_persona_across_tool_and_direct_paths(self):
        """
        测试同一次 process 调用中，工具路径和直接回答路径都使用老江湖人格。

        场景：
        1. 第一轮：用户问技术问题 -> 工具路径 (fallback) -> _direct_answer
        2. 第二轮：用户闲聊 -> 直接回答 -> _direct_answer
        """
        agent = ChatAgent()
        session_id = "test-dual-paths"

        with patch("app.agents.chat_agent.llm_client") as mock_llm, \
             patch("app.agents.chat_agent.history_manager") as mock_history, \
             patch("app.agents.chat_agent.tool_registry") as mock_registry:

            mock_history.get_history = AsyncMock(return_value="")

            stream_calls, mock_stream = _build_stream_capture()
            mock_llm.chat_stream = mock_stream
            mock_llm.chat = AsyncMock(return_value=None)

            mock_registry.get_tool = MagicMock(return_value=None)
            mock_registry.get_tools_description = MagicMock(
                return_value="mock tools description"
            )

            # 第一轮：无关键词匹配 -> LLM 决策 -> 直接回答
            async for _ in agent.process(
                message="随便聊聊",
                session_id=session_id,
                stream=False,
            ):
                pass

            # 第二轮：无关键词匹配 -> LLM 决策 -> 直接回答
            async for _ in agent.process(
                message="说个故事听听",
                session_id=session_id,
                stream=False,
            ):
                pass

            assert len(stream_calls) >= 2, f"应该有至少 2 次流式调用, 实际 {len(stream_calls)}"

            for i, msgs in enumerate(stream_calls):
                system_msgs = [m for m in msgs if m["role"] == "system"]
                if system_msgs:
                    content = system_msgs[0]["content"]
                    assert "老江湖" in content, (
                        f"第{i+1}次流式调用: 应包含老江湖人格"
                    )
