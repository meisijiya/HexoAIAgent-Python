"""
对话历史管理器模块

负责：
- 对话历史存储和获取
- 历史压缩和摘要
- Token 数量控制
"""
from typing import List, Dict, Optional
from loguru import logger

from app.core.redis import get_session_context, add_message_to_context
from app.core.llm import llm_client


class HistoryManager:
    """
    对话历史管理器
    
    功能：
    - 获取对话历史
    - 历史压缩
    - Token 控制
    """
    
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
            max_tokens: 最大 Token 数（近似）
            max_message_length: 单条消息最大长度
        """
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self.max_message_length = max_message_length
    
    async def get_history(
        self,
        session_id: str,
        format_type: str = "text"
    ) -> str:
        """
        获取对话历史
        
        Args:
            session_id: 会话 ID
            format_type: 格式类型（text/markdown）
        
        Returns:
            str: 格式化的对话历史
        """
        
        # 获取原始消息
        messages = await get_session_context(session_id, self.max_messages)
        
        if not messages:
            return ""
        
        # 压缩历史
        compressed = await self._compress_history(messages)
        
        # 格式化
        if format_type == "markdown":
            return self._format_markdown(compressed)
        else:
            return self._format_text(compressed)
    
    async def _compress_history(self, messages: List[Dict]) -> List[Dict]:
        """
        压缩对话历史
        
        策略：
        1. 截断长消息
        2. 如果超过最大数量，只保留最近的
        3. 如果超过 Token 限制，进行摘要
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
        
        # 计算总 Token 数（近似）
        total_tokens = sum(len(m["content"]) for m in compressed)
        
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
    
    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str
    ):
        """
        保存消息到历史
        
        Args:
            session_id: 会话 ID
            role: 消息角色（user/assistant）
            content: 消息内容
        """
        
        await add_message_to_context(session_id, role, content)


# 全局实例
history_manager = HistoryManager()
