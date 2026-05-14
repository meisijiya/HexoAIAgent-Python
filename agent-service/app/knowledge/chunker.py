"""
文章分块模块（优化版）

负责：
- 将 Markdown 文章按优化策略分块
- 增加分块大小（500-1000 字符）
- 增加重叠区域（100 字符）
- 按语义边界分块
"""
import re
from typing import List, Dict, Any
from loguru import logger


def chunk_markdown(content: str, file_path: str = "", min_chunk_size: int = 500, max_chunk_size: int = 1000, chunk_overlap: int = 100) -> List[Dict[str, Any]]:
    """
    将 Markdown 文章分块（优化版）
    
    Args:
        content: Markdown 文章内容
        file_path: 文件路径（用于 metadata）
        min_chunk_size: 最小分块大小（字符数）
        max_chunk_size: 最大分块大小（字符数）
        chunk_overlap: 重叠区域大小（字符数）
    
    Returns:
        List[Dict]: 分块列表，每个分块包含 content 和 metadata
    """
    if not content.strip():
        return []
    
    # 阶段 1: 按 Markdown 标题切分
    sections = split_by_headers(content)
    
    # 阶段 2: 按字符数二次分割（带重叠）
    chunks = []
    for section in sections:
        if len(section) <= max_chunk_size:
            chunks.append(section)
        else:
            chunks.extend(split_by_size_with_overlap(section, max_chunk_size, chunk_overlap))
    
    # 阶段 3: 合并过小分片
    merged_chunks = merge_small_chunks(chunks, min_chunk_size)
    
    # 构建结果
    result = []
    for i, chunk in enumerate(merged_chunks):
        if chunk.strip():  # 跳过空内容
            result.append({
                "content": chunk.strip(),
                "metadata": {
                    "_source": file_path,
                    "chunk_index": i,
                    "total_chunks": len(merged_chunks)
                }
            })
    
    logger.info(f"文章分块完成: {file_path}, 共 {len(result)} 个分块")
    return result


def split_by_headers(content: str) -> List[str]:
    """
    按 Markdown 标题切分
    
    Args:
        content: Markdown 内容
    
    Returns:
        List[str]: 按标题切分后的段落列表
    """
    # 匹配 Markdown 标题（# ## ### 等）
    header_pattern = r'^(#{1,6})\s+.+$'
    
    sections = []
    current_section = []
    
    for line in content.split('\n'):
        if re.match(header_pattern, line, re.MULTILINE):
            # 遇到新标题，保存当前段落
            if current_section:
                sections.append('\n'.join(current_section))
            current_section = [line]
        else:
            current_section.append(line)
    
    # 保存最后一个段落
    if current_section:
        sections.append('\n'.join(current_section))
    
    return sections


def split_by_size_with_overlap(text: str, max_size: int, overlap: int) -> List[str]:
    """
    按字符数分割文本（带重叠）
    
    Args:
        text: 文本内容
        max_size: 最大分块大小
        overlap: 重叠区域大小
    
    Returns:
        List[str]: 分割后的文本列表
    """
    if len(text) <= max_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + max_size
        
        # 如果不是最后一块，尝试在句子边界分割
        if end < len(text):
            # 找到最近的句子结束符
            for sep in ["。", "！", "？", ".", "!", "?", "\n"]:
                last_sep = text[start:end].rfind(sep)
                if last_sep > max_size * 0.5:  # 至少 50% 的内容
                    end = start + last_sep + 1
                    break
        
        chunks.append(text[start:end])
        start = end - overlap  # 重叠区域
    
    return chunks


def merge_small_chunks(chunks: List[str], min_size: int) -> List[str]:
    """
    合并过小的分块
    
    Args:
        chunks: 分块列表
        min_size: 最小分块大小
    
    Returns:
        List[str]: 合并后的分块列表
    """
    if not chunks:
        return []
    
    merged = []
    current_chunk = chunks[0]
    
    for i in range(1, len(chunks)):
        if len(current_chunk) < min_size:
            # 当前分块太小，与下一个合并
            current_chunk += '\n\n' + chunks[i]
        else:
            merged.append(current_chunk)
            current_chunk = chunks[i]
    
    # 保存最后一个分块
    if current_chunk:
        merged.append(current_chunk)
    
    return merged
