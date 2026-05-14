"""
文章分块模块

负责：
- 将 Markdown 文章按三阶段策略分块
- 第一阶段：按 Markdown 标题切分
- 第二阶段：按字符数二次分割
- 第三阶段：合并过小分片
"""
import re
from typing import List, Dict, Any
from loguru import logger


def chunk_markdown(content: str, file_path: str = "", min_chunk_size: int = 300, max_chunk_size: int = 500) -> List[Dict[str, Any]]:
    """
    将 Markdown 文章分块（三阶段策略）
    
    Args:
        content: Markdown 文章内容
        file_path: 文件路径（用于 metadata）
        min_chunk_size: 最小分块大小（字符数）
        max_chunk_size: 最大分块大小（字符数）
    
    Returns:
        List[Dict]: 分块列表，每个分块包含 content 和 metadata
    """
    if not content.strip():
        return []
    
    # 阶段 1: 按 Markdown 标题切分
    sections = split_by_headers(content)
    
    # 阶段 2: 按字符数二次分割
    chunks = []
    for section in sections:
        if len(section) <= max_chunk_size:
            chunks.append(section)
        else:
            chunks.extend(split_by_size(section, max_chunk_size))
    
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


def split_by_size(text: str, max_size: int) -> List[str]:
    """
    按字符数分割文本
    
    Args:
        text: 文本内容
        max_size: 最大分块大小
    
    Returns:
        List[str]: 分割后的文本列表
    """
    # 优先按段落分割
    paragraphs = text.split('\n\n')
    
    chunks = []
    current_chunk = []
    current_size = 0
    
    for para in paragraphs:
        if current_size + len(para) <= max_size:
            current_chunk.append(para)
            current_size += len(para)
        else:
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
            # 如果单个段落太长，按句子分割
            if len(para) > max_size:
                chunks.extend(split_by_sentences(para, max_size))
            else:
                current_chunk = [para]
                current_size = len(para)
    
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))
    
    return chunks


def split_by_sentences(text: str, max_size: int) -> List[str]:
    """
    按句子分割文本
    
    Args:
        text: 文本内容
        max_size: 最大分块大小
    
    Returns:
        List[str]: 分割后的文本列表
    """
    # 中英文句子分隔符
    sentence_endings = r'([。！？.!?])'
    
    sentences = re.split(sentence_endings, text)
    
    # 重新组合句子和标点
    combined_sentences = []
    for i in range(0, len(sentences) - 1, 2):
        combined_sentences.append(sentences[i] + sentences[i + 1])
    if len(sentences) % 2 == 1:
        combined_sentences.append(sentences[-1])
    
    chunks = []
    current_chunk = []
    current_size = 0
    
    for sentence in combined_sentences:
        if current_size + len(sentence) <= max_size:
            current_chunk.append(sentence)
            current_size += len(sentence)
        else:
            if current_chunk:
                chunks.append(''.join(current_chunk))
            current_chunk = [sentence]
            current_size = len(sentence)
    
    if current_chunk:
        chunks.append(''.join(current_chunk))
    
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
