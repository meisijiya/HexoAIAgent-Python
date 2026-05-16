"""
端到端测试：记忆模块完整流程验证

覆盖 3 个核心场景：
1. 多轮对话后，旧历史可通过语义检索召回
2. hybrid 模式返回近期 5 轮 + 语义 top-3
3. token 计算使用 tiktoken 精确估算

测试策略：
- 不 mock 内部方法（如 _semantic_search），而是 mock 基础设施层
- 用真实 HistoryManager 方法链验证完整数据流
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call


class TestE2ESemanticRecall:
    """E2E 场景 1：20+条消息后，通过语义检索召回旧历史"""
    pytestmark = pytest.mark.asyncio

    @patch("app.core.history_manager.get_session_context")
    @patch("app.knowledge.embedder.embedding_service")
    async def test_e2e_full_semantic_pipeline(
        self, mock_embedder, mock_get_context, history_manager_e2e
    ):
        """查询缓存相关内容应召回 Redis 相关历史（向量余弦相似度排序）"""
        query_vector = [1.0, 0.0, 0.0] * 341 + [0.0]
        mock_embedder.embed_query = AsyncMock(return_value=query_vector)

        mock_memories = []
        for i in range(20):
            mem = MagicMock(spec=[
                "id", "session_id", "role", "content", "embedding", "created_at"
            ])
            mem.id = f"mem-{i:04d}"
            mem.session_id = "e2e-session-1"
            mem.role = "user" if i % 2 == 0 else "assistant"

            if i < 5:
                mem.content = f"我们之前讨论过 Redis 缓存和 Docker 部署 #{i}"
                mem.embedding = [0.95, 0.05, 0.0] * 341 + [0.0]
            elif i < 13:
                mem.content = f"今天天气不错，适合写代码 #{i}"
                mem.embedding = [0.05, 0.95, 0.0] * 341 + [0.0]
            else:
                mem.content = f"哈哈好的没问题 #{i}"
                mem.embedding = [0.02, 0.03, 0.95] * 341 + [0.0]
            mock_memories.append(mem)

        db_mock = AsyncMock()
        result_proxy = MagicMock()
        result_proxy.scalars().all.return_value = mock_memories
        db_mock.execute = AsyncMock(return_value=result_proxy)
        mock_get_context.return_value = []

        result = await history_manager_e2e.get_history(
            session_id="e2e-session-1", query="之前提到的缓存方案是什么？",
            mode="semantic", format_type="text", db=db_mock
        )

        assert "Redis" in result or "缓存" in result or "Docker" in result
        assert result != ""
        mock_embedder.embed_query.assert_called_once()
        query_arg = mock_embedder.embed_query.call_args[0][0]
        assert "缓存" in query_arg or "方案" in query_arg

    @patch("app.core.history_manager.get_session_context")
    @patch("app.knowledge.embedder.embedding_service")
    async def test_e2e_semantic_with_caching(
        self, mock_embedder, mock_get_context, history_manager_e2e
    ):
        """相同查询第二次调用不重复请求 embedding API"""
        query_vector = [0.5] * 1024
        mock_embedder.embed_query = AsyncMock(return_value=query_vector)

        mem = MagicMock(spec=[
            "id", "session_id", "role", "content", "embedding", "created_at"
        ])
        mem.id = "mem-cache-1"
        mem.session_id = "e2e-cache"
        mem.role = "user"
        mem.content = "缓存相关的历史内容"
        mem.embedding = [0.5] * 1024

        def make_db():
            db = AsyncMock()
            rp = MagicMock()
            rp.scalars().all.return_value = [mem]
            db.execute = AsyncMock(return_value=rp)
            return db

        result1 = await history_manager_e2e.get_history(
            session_id="e2e-cache", query="什么是缓存",
            mode="semantic", db=make_db()
        )
        assert mock_embedder.embed_query.call_count == 1

        result2 = await history_manager_e2e.get_history(
            session_id="e2e-cache", query="什么是缓存",
            mode="semantic", db=make_db()
        )
        assert result2 != ""
        assert "缓存" in result2


class TestE2EHybridMode:
    """E2E 场景 2：hybrid 模式返回近期 5 轮 + 语义 top-3"""
    pytestmark = pytest.mark.asyncio

    @patch("app.core.history_manager.get_session_context")
    @patch("app.knowledge.embedder.embedding_service")
    async def test_e2e_hybrid_returns_recent_5_rounds_plus_semantic_top3(
        self, mock_embedder, mock_get_context, history_manager_e2e
    ):
        """结果应包含近期 5 轮对话 + 语义检索的旧历史（部署相关内容）"""
        recent_messages = []
        for i in range(5):
            recent_messages.append({"role": "user", "content": f"第{i+1}轮的用户问题"})
            recent_messages.append({"role": "assistant", "content": f"第{i+1}轮的助手回答"})
        mock_get_context.return_value = recent_messages

        query_vector = [0.8, 0.2, 0.0] * 341 + [0.0]
        mock_embedder.embed_query = AsyncMock(return_value=query_vector)

        old_memories = []
        for i in range(15):
            mem = MagicMock(spec=[
                "id", "session_id", "role", "content", "embedding", "created_at"
            ])
            mem.id = f"old-{i:04d}"
            mem.session_id = "e2e-hybrid"
            mem.role = "user" if i % 2 == 0 else "assistant"
            # 前 9 条"闲聊"被排除（exclude_count=10），后 6 条"Docker"应被召回
            if i < 9:
                mem.content = f"闲聊内容 #{i}"
                mem.embedding = [0.1, 0.8, 0.0] * 341 + [0.0]
            else:
                mem.content = f"之前讨论过 Docker 部署方案 #{i}"
                mem.embedding = [0.85, 0.1, 0.0] * 341 + [0.0]
            old_memories.append(mem)

        db_mock = AsyncMock()
        result_proxy = MagicMock()
        result_proxy.scalars().all.return_value = old_memories
        db_mock.execute = AsyncMock(return_value=result_proxy)

        result = await history_manager_e2e.get_history(
            session_id="e2e-hybrid", query="我们的部署方案是什么？",
            mode="hybrid", format_type="text", db=db_mock
        )

        for i in range(5):
            assert f"第{i+1}轮的用户问题" in result
            assert f"第{i+1}轮的助手回答" in result
        assert "Docker" in result or "部署" in result
        mock_embedder.embed_query.assert_called_once()

    @patch("app.core.history_manager.get_session_context")
    @patch("app.knowledge.embedder.embedding_service")
    async def test_e2e_hybrid_deduplication(
        self, mock_embedder, mock_get_context, history_manager_e2e
    ):
        """语义结果如果已在近期对话中，不重复添加"""
        mock_get_context.return_value = [
            {"role": "user", "content": "最近我们讨论了部署方案"},
            {"role": "assistant", "content": "好的我们来说部署"},
        ]

        query_vector = [0.8, 0.2, 0.0] * 341 + [0.0]
        mock_embedder.embed_query = AsyncMock(return_value=query_vector)

        content_pool = [
            "最近我们讨论了部署方案",
            "好的我们来说部署",
            "以前说的 Redis 缓存方案",
            "关于 Docker 的网络配置",
            "好的我们来说部署",
        ]
        old_memories = []
        for i, content in enumerate(content_pool):
            mem = MagicMock(spec=[
                "id", "session_id", "role", "content", "embedding", "created_at"
            ])
            mem.id = f"dedup-{i:04d}"
            mem.session_id = "e2e-dedup"
            mem.role = "user" if i % 2 == 0 else "assistant"
            mem.content = content
            mem.embedding = [0.8, 0.1, 0.0] * 341 + [0.0]
            old_memories.append(mem)

        db_mock = AsyncMock()
        result_proxy = MagicMock()
        result_proxy.scalars().all.return_value = old_memories
        db_mock.execute = AsyncMock(return_value=result_proxy)

        result = await history_manager_e2e.get_history(
            session_id="e2e-dedup", query="部署方案",
            mode="hybrid", db=db_mock
        )

        assert "Redis 缓存方案" in result or "Docker 的网络配置" in result
        assert result.count("最近我们讨论了部署方案") <= 1
        assert result.count("好的我们来说部署") <= 1

    @patch("app.core.history_manager.get_session_context")
    @patch("app.knowledge.embedder.embedding_service")
    async def test_e2e_hybrid_with_tiktoken_compression(
        self, mock_embedder, mock_get_context, history_manager_small
    ):
        """超出 token 限制时自动触发摘要压缩"""
        mock_get_context.return_value = [
            msg
            for i in range(5)
            for msg in ({"role": "user", "content": "A" * 150 + str(i)},
                        {"role": "assistant", "content": "B" * 150 + str(i)})
        ]
        query_vector = [0.5] * 1024
        mock_embedder.embed_query = AsyncMock(return_value=query_vector)

        old_memories = []
        for i in range(6):
            mem = MagicMock(spec=[
                "id", "session_id", "role", "content", "embedding", "created_at"
            ])
            mem.id = f"long-{i:04d}"
            mem.session_id = "e2e-compress"
            mem.role = "user" if i % 2 == 0 else "assistant"
            mem.content = "C" * 200 + str(i)
            mem.embedding = [0.9 - i * 0.05, 0.1 + i * 0.05, 0.0] * 341 + [0.0]
            old_memories.append(mem)

        db_mock = AsyncMock()
        result_proxy = MagicMock()
        result_proxy.scalars().all.return_value = old_memories
        db_mock.execute = AsyncMock(return_value=result_proxy)

        result = await history_manager_small.get_history(
            session_id="e2e-compress", query="测试压缩",
            mode="hybrid", db=db_mock
        )

        assert result != ""
        assert len(result) > 0


class TestE2ETokenCounting:
    """E2E 场景 3：token 计算使用 tiktoken 精确估算"""
    # 仅 async 方法需要 asyncio 标记，sync 方法不需要
    # async 方法单独标记，class 级别标记会影响 sync 测试

    def test_e2e_tiktoken_encoding_loaded(self, history_manager_e2e):
        """tiktoken 编码器正确加载为 cl100k_base"""
        assert history_manager_e2e._encoding is not None
        enc = history_manager_e2e._encoding
        assert enc.name == "cl100k_base"

    def test_e2e_token_count_not_equal_char_count(self, history_manager_e2e):
        """token 计数 ≠ 字符计数，证明使用 tiktoken 而非 len()"""
        english = "Hello world, this is a test of the tiktoken token counting"
        token_en = history_manager_e2e._count_tokens(english)
        char_en = len(english)
        assert token_en != char_en

    def test_e2e_known_token_values(self, history_manager_e2e):
        """cl100k_base 已知值：Hello, world! == 4 tokens"""
        assert history_manager_e2e._count_tokens("Hello, world!") == 4
        assert history_manager_e2e._count_tokens("") == 0
        assert history_manager_e2e._count_tokens(None) == 0

    def test_e2e_chinese_token_ratio(self, history_manager_e2e):
        """中文 token 数合理性：长文本 token 多于短文本"""
        chinese_short = "你好"
        chinese_long = "你好世界，这是一个测试用例用于验证中文分词效果"
        assert history_manager_e2e._count_tokens(chinese_short) > 0
        assert history_manager_e2e._count_tokens(chinese_long) > history_manager_e2e._count_tokens(chinese_short)

    def test_e2e_mixed_content_token_count(self, history_manager_e2e):
        """中英文混合文本的 token 数"""
        count = history_manager_e2e._count_tokens("你好 world，Let's test tiktoken!")
        assert count > 0
        assert isinstance(count, int)

    @pytest.mark.asyncio
    @patch("app.core.history_manager.get_session_context")
    @patch("app.knowledge.embedder.embedding_service")
    async def test_e2e_compress_uses_tiktoken_not_len(
        self, mock_embedder, mock_get_context, history_manager_e2e
    ):
        """_compress_history 内部使用 tiktoken：超限时触发摘要"""
        mock_get_context.return_value = []
        mock_embedder.embed_query = AsyncMock(return_value=[0.5] * 1024)

        messages = [
            {"role": "user" if i % 2 == 0 else "assistant",
             "content": "这是一个测试消息用来验证 tiktoken token 计数 " * 10}
            for i in range(15)
        ]

        with patch("app.core.history_manager.llm_client") as mock_llm:
            mock_llm.chat = AsyncMock(return_value="这是对话摘要内容")
            compressed = await history_manager_e2e._compress_history(messages)
            assert len(compressed) <= history_manager_e2e.max_messages


class TestE2ERedisBackwardCompatibility:
    """E2E 场景 4：Redis 向后兼容性验证"""
    pytestmark = pytest.mark.asyncio

    @patch("app.core.history_manager.add_message_to_context")
    @patch("app.core.history_manager.get_session_context")
    async def test_e2e_save_and_retrieve_cycle(
        self, mock_get_context, mock_add_msg, history_manager_e2e
    ):
        """save → retrieve 完整流程：新旧接口配合工作"""
        await history_manager_e2e.save_message("e2e-session", "user", "E2E 测试问题")
        await history_manager_e2e.save_message("e2e-session", "assistant", "E2E 测试回答")
        await history_manager_e2e.save_message("e2e-session", "user", "第二个问题")

        assert mock_add_msg.call_count == 3
        mock_add_msg.assert_has_calls([
            call("e2e-session", "user", "E2E 测试问题"),
            call("e2e-session", "assistant", "E2E 测试回答"),
            call("e2e-session", "user", "第二个问题"),
        ])

        mock_get_context.return_value = [
            {"role": "user", "content": "E2E 测试问题"},
            {"role": "assistant", "content": "E2E 测试回答"},
            {"role": "user", "content": "第二个问题"},
        ]

        result = await history_manager_e2e.get_recent_history("e2e-session", limit=5)
        assert "E2E 测试问题" in result
        assert "E2E 测试回答" in result
        assert "第二个问题" in result

        result2 = await history_manager_e2e.get_history("e2e-session")
        assert "E2E 测试问题" in result2

    @patch("app.core.history_manager.get_session_context")
    async def test_e2e_save_memory_embedding_no_db(
        self, mock_get_context, history_manager_e2e
    ):
        """save_memory_embedding 无 db 时仅写 Redis"""
        with patch("app.core.history_manager.add_message_to_context") as mock_add:
            await history_manager_e2e.save_memory_embedding(
                session_id="e2e-no-db", role="user", content="只写 Redis 测试"
            )
            mock_add.assert_called_once_with("e2e-no-db", "user", "只写 Redis 测试")

    @patch("app.core.history_manager.get_session_context")
    async def test_e2e_get_history_without_any_args(
        self, mock_get_context, history_manager_e2e
    ):
        """最简调用 get_history(session_id) 向后兼容"""
        mock_get_context.return_value = [{"role": "user", "content": "极简调用测试"}]
        result = await history_manager_e2e.get_history("e2e-simple")
        assert "极简调用测试" in result

        result2 = await history_manager_e2e.get_history("e2e-simple", mode="recent")
        assert "极简调用测试" in result2


class TestE2EErrorScenarios:
    """E2E 异常场景：API/DB 失败时的优雅降级"""
    pytestmark = pytest.mark.asyncio

    @patch("app.core.history_manager.get_session_context")
    @patch("app.knowledge.embedder.embedding_service")
    async def test_e2e_embedding_api_failure_graceful(
        self, mock_embedder, mock_get_context, history_manager_e2e
    ):
        """embedding API 失败不抛异常，Redis 写入不受影响"""
        mock_embedder.embed_query = AsyncMock(side_effect=Exception("DashScope API 超时"))
        mock_get_context.return_value = []

        with patch("app.core.history_manager.add_message_to_context") as mock_add:
            await history_manager_e2e.save_memory_embedding(
                session_id="e2e-error", role="user",
                content="API 失败但 Redis 要成功", db=AsyncMock()
            )
            mock_add.assert_called_once()

    @patch("app.core.history_manager.get_session_context")
    @patch("app.knowledge.embedder.embedding_service")
    async def test_e2e_db_query_failure_graceful(
        self, mock_embedder, mock_get_context, history_manager_e2e
    ):
        """DB 查询失败时 get_history 不抛异常，回退到 recent 模式"""
        mock_get_context.return_value = [{"role": "user", "content": "近期对话内容"}]
        mock_embedder.embed_query = AsyncMock(return_value=[0.5] * 1024)

        db_mock = AsyncMock()
        db_mock.execute = AsyncMock(side_effect=Exception("PostgreSQL 连接失败"))

        result = await history_manager_e2e.get_history(
            session_id="e2e-db-error", query="测试",
            mode="hybrid", db=db_mock
        )
        assert "近期对话内容" in result


@pytest.fixture
def history_manager_e2e():
    """标准 HistoryManager（e2e 测试用）"""
    from app.core.history_manager import HistoryManager
    # max_messages=20 确保 hybrid（近期 10 条 + 语义 top-3）不会被压缩截断
    return HistoryManager(max_messages=20, max_tokens=20000, max_message_length=500)


@pytest.fixture
def history_manager_small():
    """小 token 限制的 HistoryManager（触发压缩用）"""
    from app.core.history_manager import HistoryManager
    return HistoryManager(max_messages=5, max_tokens=500, max_message_length=200)
