"""
工具函数模块

提供常用的辅助函数
"""
import uuid
from datetime import datetime
from typing import Optional


def generate_uuid() -> str:
    """
    生成 UUID
    
    Returns:
        str: UUID 字符串
    """
    return str(uuid.uuid4())


def get_current_time() -> datetime:
    """
    获取当前时间（UTC）
    
    Returns:
        datetime: 当前时间
    """
    return datetime.utcnow()


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    截断文本
    
    Args:
        text: 原始文本
        max_length: 最大长度
        suffix: 后缀
    
    Returns:
        str: 截断后的文本
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def sanitize_filename(filename: str) -> str:
    """
    清理文件名，移除非法字符
    
    Args:
        filename: 原始文件名
    
    Returns:
        str: 清理后的文件名
    """
    import re
    # 只保留字母、数字、中文、下划线、连字符
    sanitized = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', filename)
    # 移除连续的下划线
    sanitized = re.sub(r'_+', '_', sanitized)
    # 移除首尾下划线
    sanitized = sanitized.strip('_')
    return sanitized


def extract_urls(text: str) -> list:
    """
    从文本中提取 URL
    
    Args:
        text: 文本内容
    
    Returns:
        list: URL 列表
    """
    import re
    url_pattern = r'https?://[^\s<>\"\'\)\]]+'
    return re.findall(url_pattern, text)


def is_valid_url(url: str) -> bool:
    """
    验证 URL 是否有效
    
    Args:
        url: URL 字符串
    
    Returns:
        bool: 是否有效
    """
    import re
    url_pattern = r'^https?://[^\s<>\"\'\)\]]+$'
    return bool(re.match(url_pattern, url))
