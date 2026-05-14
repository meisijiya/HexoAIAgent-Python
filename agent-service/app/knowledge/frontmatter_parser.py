"""
Front-matter 解析模块

负责：
- 解析 Markdown 文件的 front-matter
- 提取 title、categories、tags 等元数据
- 支持多种 categories 格式
"""
import re
import yaml
from typing import Dict, Any, List, Optional
from loguru import logger


def parse_frontmatter(content: str) -> Dict[str, Any]:
    """
    解析 Markdown 文件的 front-matter
    
    Args:
        content: Markdown 文件内容
    
    Returns:
        Dict: 包含 front-matter 数据的字典
    
    示例输入：
        ---
        title: Redis 分布式锁
        categories:
          - [java, 黑马点评]
        tags:
          - Redis
          - 分布式锁
        ---
    
    示例输出：
        {
            "title": "Redis 分布式锁",
            "categories": ["java", "黑马点评"],
            "tags": ["Redis", "分布式锁"]
        }
    """
    
    # 匹配 front-matter（--- 之间的内容）
    pattern = r'^---\s*\n(.*?)\n---\s*\n'
    match = re.match(pattern, content, re.DOTALL)
    
    if not match:
        logger.debug("未找到 front-matter")
        return {}
    
    frontmatter_text = match.group(1)
    
    try:
        # 使用 YAML 解析
        data = yaml.safe_load(frontmatter_text)
        
        if not isinstance(data, dict):
            return {}
        
        # 标准化 categories
        if "categories" in data:
            data["categories"] = normalize_categories(data["categories"])
        
        # 标准化 tags
        if "tags" in data:
            data["tags"] = normalize_tags(data["tags"])
        
        return data
        
    except yaml.YAMLError as e:
        logger.warning(f"YAML 解析失败: {e}")
        return {}


def normalize_categories(categories: Any) -> List[str]:
    """
    标准化 categories 格式
    
    支持的格式：
    1. 单层列表: ["java", "python"]
    2. 嵌套列表: [["java", "黑马点评"], ["python", "教程"]]
    3. 混合格式: ["java", ["黑马点评", "Redis"]]
    4. 单个字符串: "java"
    
    Args:
        categories: 原始 categories 数据
    
    Returns:
        List[str]: 标准化后的分类列表
    """
    
    if not categories:
        return []
    
    # 单个字符串
    if isinstance(categories, str):
        return [categories]
    
    # 列表格式
    if isinstance(categories, list):
        result = []
        for item in categories:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, list):
                # 嵌套列表，展开
                result.extend([str(i) for i in item])
        return result
    
    return []


def normalize_tags(tags: Any) -> List[str]:
    """
    标准化 tags 格式
    
    支持的格式：
    1. 列表: ["Redis", "分布式锁"]
    2. 单个字符串: "Redis"
    
    Args:
        tags: 原始 tags 数据
    
    Returns:
        List[str]: 标准化后的标签列表
    """
    
    if not tags:
        return []
    
    # 单个字符串
    if isinstance(tags, str):
        return [tags]
    
    # 列表格式
    if isinstance(tags, list):
        return [str(tag) for tag in tags]
    
    return []


def extract_title(content: str) -> Optional[str]:
    """
    从 front-matter 提取标题
    
    Args:
        content: Markdown 文件内容
    
    Returns:
        Optional[str]: 标题
    """
    
    data = parse_frontmatter(content)
    return data.get("title")


def extract_categories(content: str) -> List[str]:
    """
    从 front-matter 提取分类
    
    Args:
        content: Markdown 文件内容
    
    Returns:
        List[str]: 分类列表
    """
    
    data = parse_frontmatter(content)
    return data.get("categories", [])


def extract_tags(content: str) -> List[str]:
    """
    从 front-matter 提取标签
    
    Args:
        content: Markdown 文件内容
    
    Returns:
        List[str]: 标签列表
    """
    
    data = parse_frontmatter(content)
    return data.get("tags", [])


def format_categories(categories: List[str]) -> str:
    """
    格式化分类显示
    
    Args:
        categories: 分类列表
    
    Returns:
        str: 格式化后的分类字符串
    
    示例：
        输入: ["java", "黑马点评"]
        输出: "[java/黑马点评]"
    """
    
    if not categories:
        return ""
    
    return "[" + "/".join(categories) + "]"


# 测试代码
if __name__ == "__main__":
    # 测试 front-matter 解析
    test_content = """---
title: Redis 分布式锁
author: 老江湖
tags:
  - Redis
  - 分布式锁
categories:
  - [java, 黑马点评]
date: 2025-10-12 00:00:00
---

# 正文内容
"""
    
    data = parse_frontmatter(test_content)
    print(f"标题: {data.get('title')}")
    print(f"分类: {data.get('categories')}")
    print(f"标签: {data.get('tags')}")
    print(f"格式化分类: {format_categories(data.get('categories', []))}")
