"""
对话历史管理器模块（优化版）

负责：
- 对话历史存储和获取
- 历史压缩和摘要
- Token 精确计数（tiktoken）
- 滑动窗口 + 语义检索混合模式
"""
import os
import math
import json
from typing import List, Dict, Optional
from loguru import logger
import tiktoken

from app.core.redis import get_session_context, add_message_to_context
from app.core.llm import llm_client


# 对话历史轮数（从环境变量读取，默认 3 轮）
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "5"))

# tiktoken 编码名称（与 text-embedding-v4 兼容的编码器）
TIKTOKEN_ENCODING = "cl100k_base"

# 混合模式配置
HYBRID_RECENT_ROUNDS = 5   # 近期直接返回的轮数
HYBRID_SEMANTIC_TOP_K = 3  # 语义检索返回的旧历史条数


class HistoryManager:
    """对话历史管理器（支持滑动窗口 + 语义检索混合模式）"""
    
    def __init__(
        self,
        max_messages: int = 10,
        max_tokens: int = 2000,
        max_message_length: int = 200
    ):
        """
        初始化

        Args:
            max_messages: 最大消息数
            max_tokens: 最大 Token 数（精确计数）
            max_message_length: 单条消息最大长度
        """
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self.max_message_length = max_message_length
        self._encoding = tiktoken.get_encoding(TIKTOKEN_ENCODING)
        self._last_semantic_info = {}  # 最近一次语义检索结果

    # ==================== Token 精确计数 ====================

    def _count_tokens(self, text: str) -> int:
        """
        使用 tiktoken 精确计算 token 数

        Args:
            text: 文本内容

        Returns:
            int: token 数量
        """
        if not text:
            return 0
        return len(self._encoding.encode(text))

    # ==================== 核心接口（支持三种模式） ====================

    async def get_history(
        self,
        session_id: str,
        query: str = None,
        mode: str = "hybrid",
        format_type: str = "text",
        db=None
    ) -> str:
        """
        获取对话历史（支持三种模式）

        Args:
            session_id: 会话 ID
            query: 当前查询（semantic/hybrid 模式需要）
            mode: 检索模式（recent / semantic / hybrid）
            format_type: 格式类型（text / markdown）
            db: 数据库会话（semantic/hybrid 模式需要，为 None 时回退到 recent）

        Returns:
            str: 格式化的对话历史
        """
        if mode == "semantic":
            if not db:
                logger.warning("semantic 模式需要 db 参数，回退到 recent 模式")
                return await self.get_recent_history(session_id, format_type=format_type)
            return await self._get_semantic_context(session_id, query, format_type, db)
        elif mode == "hybrid":
            if not db:
                logger.warning("hybrid 模式需要 db 参数，回退到 recent 模式")
                return await self.get_recent_history(session_id, format_type=format_type)
            return await self._get_hybrid_context(session_id, query, format_type, db)
        else:
            # recent 模式（向后兼容）
            return await self.get_recent_history(session_id, format_type=format_type)

    async def _get_semantic_context(
        self,
        session_id: str,
        query: str,
        format_type: str = "text",
        db=None
    ) -> str:
        """
        纯语义检索模式：完全通过 pgvector 搜索相关历史

        Args:
            session_id: 会话 ID
            query: 当前查询文本
            format_type: 格式类型
            db: 数据库会话

        Returns:
            str: 格式化的语义检索结果
        """
        if not query or not db:
            return ""

        semantic_messages = await self._semantic_search(
            db, session_id, query, exclude_count=0, top_k=5
        )
        if not semantic_messages:
            return ""

        if format_type == "markdown":
            return self._format_markdown(semantic_messages)
        else:
            return self._format_text(semantic_messages)

    async def _get_hybrid_context(
        self,
        session_id: str,
        query: str = None,
        format_type: str = "text",
        db=None
    ) -> str:
        """
        混合模式：近期 5 轮直接返回 + 旧历史 embedding 语义检索 top-K

        策略:
        1. 从 Redis 获取最近 5 轮对话（10 条消息）
        2. 从 pgvector 获取语义相似的历史（排除近期 5 轮）
        3. 旧语义历史在前，近期对话在后

        Args:
            session_id: 会话 ID
            query: 当前查询
            format_type: 格式类型
            db: 数据库会话

        Returns:
            str: 格式化的混合上下文
        """
        # 1. 从 Redis 获取近期 5 轮（10 条消息）
        recent_messages = await get_session_context(session_id, HYBRID_RECENT_ROUNDS * 2)

        # 2. 从 pgvector 获取语义相似的历史（排除近期 5 轮）
        semantic_messages = []
        if query and db:
            try:
                # 先检索多一些用于去重
                raw_semantic = await self._semantic_search(
                    db, session_id, query,
                    exclude_count=HYBRID_RECENT_ROUNDS * 2,
                    top_k=HYBRID_SEMANTIC_TOP_K + 5
                )
                # 去重：排除已在 recent_messages 中的内容
                recent_contents = {m.get("content", "") for m in recent_messages}
                for msg in raw_semantic:
                    if msg.get("content", "") not in recent_contents:
                        semantic_messages.append(msg)
                    if len(semantic_messages) >= HYBRID_SEMANTIC_TOP_K:
                        break
            except Exception as e:
                logger.error(f"语义检索失败: {e}")

        # 3. 合并：语义历史（标注为可回顾）+ 近期对话
        if semantic_messages:
            semantic_messages.insert(0, {
                "role": "system",
                "content": "📝 以下是你们过去聊过的历史话题（用户问及过去时可以引用）："
            })
            self._last_semantic_info = {
                "found": True,
                "count": len(semantic_messages) - 1,  # 减去标题行
                "query": query[:50] if query else ""
            }
        else:
            self._last_semantic_info = {"found": False, "count": 0}
        all_messages = semantic_messages + recent_messages

        if not all_messages:
            return ""

        # 4. 压缩并格式化
        compressed = await self._compress_history(all_messages)

        if format_type == "markdown":
            return self._format_markdown(compressed)
        else:
            return self._format_text(compressed)

    # ==================== 语义检索核心 ====================

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """
        计算两个向量的余弦相似度

        Args:
            a: 向量 A
            b: 向量 B

        Returns:
            float: 余弦相似度（-1 ~ 1）
        """
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if not norm_a or not norm_b:
            return 0.0
        return dot / (norm_a * norm_b)

    async def _semantic_search(
        self,
        db,
        session_id: str,
        query: str,
        exclude_count: int = 0,
        top_k: int = 3
    ) -> List[Dict]:
        """
        语义检索历史对话

        查询 pgvector 中存储的历史对话 embedding，
        使用余弦相似度排序，返回 top-K 结果。

        Args:
            db: 数据库会话
            session_id: 会话 ID
            query: 查询文本
            exclude_count: 排除最近 N 条消息（避免与滑动窗口重复）
            top_k: 返回结果数量

        Returns:
            List[Dict]: 消息列表
        """
        from app.knowledge.embedder import embedding_service
        from sqlalchemy import select

        # 1. 生成查询向量
        query_embedding = await embedding_service.embed_query(query)

        # 2. 获取会话的所有历史记忆
        result = await db.execute(
            select(ConversationMemory)
            .where(ConversationMemory.session_id == session_id)
            .where(ConversationMemory.embedding.isnot(None))
            .order_by(ConversationMemory.created_at.desc())
        )
        all_memories = result.scalars().all()

        # 3. 排除最近 exclude_count 条消息
        if exclude_count > 0 and len(all_memories) > exclude_count:
            all_memories = all_memories[exclude_count:]

        if not all_memories:
            return []

        # 4. 计算余弦相似度
        scored = []
        for mem in all_memories:
            if not mem.embedding:
                continue
            sim = self._cosine_similarity(query_embedding, mem.embedding)
            scored.append((sim, mem))

        # 5. 按相似度排序取 top_k，过滤低于阈值的弱匹配
        scored.sort(key=lambda x: x[0], reverse=True)
        SIMILARITY_THRESHOLD = 0.45  # 低于此值视为不相关
        top = [(sim, mem) for sim, mem in scored[:top_k] if sim >= SIMILARITY_THRESHOLD]

        top_scores = [f"{sim:.3f}" for sim, _ in top] if top else ["无"]
        logger.info(
            f"语义检索: session={session_id[:8]}..., "
            f"query='{query[:30]}...', "
            f"top_k={top_k}, "
            f"found={len(top)} results, "
            f"scores=[{', '.join(top_scores)}]"
        )

        return [
            {"role": mem.role, "content": mem.content}
            for _, mem in top
        ]

    # ==================== 双写存储 ====================

    async def save_memory_embedding(
        self,
        session_id: str,
        role: str,
        content: str,
        db=None
    ):
        """
        双写存储：Redis 短期记忆 + pgvector 长期记忆

        1. 写入 Redis（短期记忆，用于 recent 模式）
        2. 写入 pgvector（长期记忆，用于 semantic/hybrid 模式）

        Args:
            session_id: 会话 ID
            role: 消息角色（user/assistant）
            content: 消息内容
            db: 数据库会话（用于写入 pgvector）
        """
        # 1. 写入 Redis（短期记忆）
        await add_message_to_context(session_id, role, content)

        # 2. 写入 pgvector（长期记忆）
        if db:
            try:
                from app.knowledge.embedder import embedding_service

                # 生成 embedding
                embedding = await embedding_service.embed_query(content)

                # 存入 ConversationMemory 表
                memory_entry = ConversationMemory(
                    session_id=session_id,
                    role=role,
                    content=content,
                    embedding=embedding,
                )
                db.add(memory_entry)
                await db.flush()

                logger.debug(
                    f"记忆已保存: session={session_id[:8]}..., "
                    f"role={role}, "
                    f"content_len={len(content)}"
                )
            except Exception as e:
                logger.error(f"保存记忆 embedding 失败: {e}")

    async def save_batch_memory(
        self,
        session_id: str,
        batch_label: str,
        user_messages_text: str,
        db=None
    ):
        """
        将一批用户消息做 embedding 后写入 pgvector conversation_memories 表

        与 save_memory_embedding 不同，本方法：
        - 不写 Redis（专注长期记忆）
        - role 固定为 "batch" 以区分单条消息
        - 附带 metadata 标识批次范围和轮次数量

        Args:
            session_id: 会话 ID
            batch_label: 批次标识，如 "rounds-1-5"
            user_messages_text: 拼接好的用户消息文本
            db: 数据库会话（用于写入 pgvector）
        """
        if not db:
            logger.warning("save_batch_memory: db 为空，跳过写入")
            return

        try:
            # 内联 import（与 save_memory_embedding 一致）
            from app.knowledge.embedder import embedding_service

            embedding_vector = await embedding_service.embed_query(user_messages_text)

            memory_entry = ConversationMemory(
                session_id=session_id,
                role="batch",
                content=user_messages_text,
                embedding=embedding_vector,
                metadata_={
                    "type": "batch",
                    "label": batch_label,
                    "round_count": 5,
                },
            )

            db.add(memory_entry)
            await db.flush()

            logger.info(
                f"批次记忆已保存: session={session_id[:8]}..., "
                f"label={batch_label}, "
                f"content_len={len(user_messages_text)}"
            )
        except Exception as e:
            logger.error(f"保存批次记忆 embedding 失败: session={session_id[:8]}..., label={batch_label}, error={e}")

    # ==================== 对话历史压缩 ====================

    async def _compress_history(self, messages: List[Dict]) -> List[Dict]:
        """
        压缩对话历史

        策略：
        1. 截断长消息
        2. 如果超过最大数量，只保留最近的
        3. 使用 tiktoken 精确计算 token，超过限制时进行摘要
        """
        # 截断长消息
        compressed = []
        for msg in messages:
            if len(msg["content"]) > self.max_message_length:
                msg = msg.copy()
                msg["content"] = msg["content"][:self.max_message_length] + "..."
            compressed.append(msg)

        # 如果超过最大数量，只保留最近的
        if len(compressed) > self.max_messages:
            compressed = compressed[-self.max_messages:]

        # 使用 tiktoken 精确计算 Token 数
        total_tokens = sum(self._count_tokens(m["content"]) for m in compressed)

        # 如果超过 Token 限制，进行摘要
        if total_tokens > self.max_tokens:
            compressed = await self._summarize_history(compressed)

        return compressed

    async def _summarize_history(self, messages: List[Dict]) -> List[Dict]:
        """
        对对话历史进行摘要

        Args:
            messages: 原始消息列表

        Returns:
            List[Dict]: 摘要后的消息列表
        """
        # 构建摘要 Prompt
        history_text = self._format_text(messages)

        prompt = f"""请将以下对话历史总结为简洁的摘要，保留关键信息：

对话历史：
{history_text}

要求：
1. 保留用户的核心问题和意图
2. 保留关键的技术术语和实体
3. 压缩到 300 字以内
4. 使用中文

摘要："""

        try:
            summary = await llm_client.chat([{"role": "user", "content": prompt}])

            # 返回摘要作为历史
            return [{
                "role": "system",
                "content": f"对话摘要：{summary}"
            }]

        except Exception as e:
            logger.error(f"历史摘要失败: {e}")
            # 如果摘要失败，只保留最近 3 条消息
            return messages[-3:]

    # ==================== 格式化 ====================

    def _format_text(self, messages: List[Dict]) -> str:
        """格式化为纯文本"""
        formatted = []
        for msg in messages:
            role = "用户" if msg["role"] == "user" else "助手"
            formatted.append(f"{role}: {msg['content']}")
        return "\n".join(formatted)

    def _format_markdown(self, messages: List[Dict]) -> str:
        """格式化为 Markdown"""
        formatted = []
        for msg in messages:
            if msg["role"] == "user":
                formatted.append(f"**用户**: {msg['content']}")
            else:
                formatted.append(f"**助手**: {msg['content']}")
        return "\n\n".join(formatted)

    def compress_for_tool(self, history: List[Dict], current_query: str) -> str:
        """
        为工具调用压缩历史

        Args:
            history: 完整对话历史
            current_query: 当前问题

        Returns:
            str: 压缩后的摘要（包含上下文和当前问题）
        """
        if not history:
            return current_query

        # 单问题场景下不压缩（只有1条消息且是用户消息）
        if len(history) == 1 and history[0].get("role") == "user":
            return current_query

        # 提取最近 2 轮对话（4条消息）
        recent = history[-4:] if len(history) >= 4 else history

        topics = self._extract_topics(history)
        summary_parts = []

        if topics:
            summary_parts.append(f"## 对话上下文\n最近讨论：{', '.join(topics)}")

        if recent:
            summary_parts.append("## 最近对话")
            for msg in recent:
                role = "用户" if msg.get("role") == "user" else "助手"
                content = msg.get("content", "")[:100]
                summary_parts.append(f"{role}: {content}")

        summary_parts.append(f"## 当前问题\n{current_query}")

        return "\n\n".join(summary_parts)

    def _extract_topics(self, history: List[Dict]) -> List[str]:
        """
        从历史中提取讨论主题（技术名词）

        Args:
            history: 对话历史

        Returns:
            List[str]: 技术名词列表（最多5个）
        """
        tech_keywords = [
            "hexo", "docker", "redis", "postgresql", "pgvector", "fastapi",
            "nginx", "linux", "git", "python", "javascript", "node",
            "react", "vue", "mysql", "mongodb", "kafka", "elasticsearch",
            "kubernetes", "aws", "azure", "ssl", "https", "api", "rest",
            "graphql", "websocket", "sse", "jwt", "oauth", "cors",
            "embedding", "vector", "llm", "agent", "rag"
        ]

        topics = set()
        for msg in history:
            content = msg.get("content", "").lower()
            for keyword in tech_keywords:
                if keyword in content:
                    topics.add(keyword.upper())

        return list(topics)[:5]

    # ==================== 近期历史（向后兼容） ====================

    async def get_recent_history(
        self,
        session_id: str,
        limit: int = None,
        format_type: str = "text"
    ) -> str:
        """
        获取最近 N 轮对话历史

        Args:
            session_id: 会话 ID
            limit: 历史轮数（默认使用 HISTORY_LIMIT 配置）
            format_type: 格式类型（text/markdown）

        Returns:
            str: 格式化的对话历史
        """
        if limit is None:
            limit = HISTORY_LIMIT

        # 计算消息数（每轮 2 条消息：用户 + 助手）
        max_messages = limit * 2

        # 获取原始消息
        messages = await get_session_context(session_id, max_messages)

        if not messages:
            return ""

        # 格式化
        if format_type == "markdown":
            return self._format_markdown(messages)
        else:
            return self._format_text(messages)

    # ==================== 保存消息（向后兼容） ====================

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str
    ):
        """
        保存消息到历史（Redis 短期记忆）

        Args:
            session_id: 会话 ID
            role: 消息角色（user/assistant）
            content: 消息内容
        """
        await add_message_to_context(session_id, role, content)


# 提前导入 ConversationMemory（避免循环依赖）
from app.models.memory import ConversationMemory


# 全局实例
history_manager = HistoryManager()
