#!/usr/bin/env python3
"""
批量导入文章脚本（优化版）

支持：
- 从 Markdown 文件夹导入文章到知识库
- 解析 front-matter 提取元数据（categories, tags）
- 自动分块和向量化
"""
import os
import re
import sys
import yaml
import requests
from pathlib import Path
from typing import List, Dict, Any

API_BASE = "http://localhost:8001"


def get_token() -> str:
    """获取匿名 Token"""
    response = requests.post(f"{API_BASE}/api/auth/anonymous")
    return response.json()["token"]


def parse_frontmatter(content: str) -> Dict[str, Any]:
    """
    解析 front-matter
    
    Args:
        content: Markdown 文件内容
    
    Returns:
        Dict: front-matter 数据
    """
    
    # 匹配 front-matter（--- 之间的内容）
    pattern = r'^---\s*\n(.*?)\n---\s*\n'
    match = re.match(pattern, content, re.DOTALL)
    
    if not match:
        return {}
    
    frontmatter_text = match.group(1)
    
    try:
        data = yaml.safe_load(frontmatter_text)
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        return {}


def normalize_categories(categories: Any) -> List[str]:
    """
    标准化 categories 格式
    """
    
    if not categories:
        return []
    
    if isinstance(categories, str):
        return [categories]
    
    if isinstance(categories, list):
        result = []
        for item in categories:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, list):
                result.extend([str(i) for i in item])
        return result
    
    return []


def normalize_tags(tags: Any) -> List[str]:
    """
    标准化 tags 格式
    """
    
    if not tags:
        return []
    
    if isinstance(tags, str):
        return [tags]
    
    if isinstance(tags, list):
        return [str(tag) for tag in tags]
    
    return []


def read_markdown_file(file_path: str) -> Dict:
    """
    读取 Markdown 文件（带 front-matter 解析）
    
    Args:
        file_path: 文件路径
    
    Returns:
        Dict: 包含标题、内容、元数据的字典
    """
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 解析 front-matter
    frontmatter = parse_frontmatter(content)
    
    # 提取标题
    title = frontmatter.get("title")
    if not title:
        # 尝试从 # 标题提取
        title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
        else:
            # 使用文件名
            title = Path(file_path).stem
    
    # 提取分类和标签
    categories = normalize_categories(frontmatter.get("categories"))
    tags = normalize_tags(frontmatter.get("tags"))
    
    # 提取相对路径（从 _posts 开始）
    posts_marker = "_posts/"
    posts_index = file_path.find(posts_marker)
    if posts_index != -1:
        relative_path = file_path[posts_index + len(posts_marker):]
    else:
        relative_path = os.path.basename(file_path)
    
    # 去掉 .md 后缀
    if relative_path.endswith(".md"):
        relative_path = relative_path[:-3]
    
    return {
        "title": title,
        "content": content,
        "url": f"file://{os.path.abspath(file_path)}",
        "source": "blog",
        "categories": categories,
        "tags": tags,
        "relative_path": relative_path,
        "author": frontmatter.get("author", ""),
        "date": str(frontmatter.get("date", ""))
    }


def import_article(token: str, article: Dict) -> bool:
    """
    导入单篇文章
    
    Args:
        token: API Token
        article: 文章数据
    
    Returns:
        bool: 是否成功
    """
    
    # 构建请求数据
    request_data = {
        "title": article["title"],
        "url": article["url"],
        "content": article["content"],
        "source": article["source"]
    }
    
    response = requests.post(
        f"{API_BASE}/api/knowledge/articles",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        },
        json=request_data
    )
    
    if response.status_code == 200:
        result = response.json()
        categories_str = "/".join(article.get("categories", []))
        tags_str = ", ".join(article.get("tags", []))
        
        print(f"   ✅ {article['title']}")
        if categories_str:
            print(f"      分类: [{categories_str}]")
        if tags_str:
            print(f"      标签: {tags_str}")
        print(f"      分块: {result.get('chunks_count', '?')} 个")
        return True
    else:
        print(f"   ❌ {article['title']}: {response.text[:100]}")
        return False


def scan_markdown_files(directory: str) -> List[str]:
    """
    扫描目录下的 Markdown 文件
    """
    
    md_files = []
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.md'):
                md_files.append(os.path.join(root, file))
    
    return sorted(md_files)


def main():
    print("📚 批量导入文章到知识库（优化版）")
    print("=" * 50)
    
    # 检查参数
    if len(sys.argv) < 2:
        print("用法: python import_articles.py <文章目录>")
        print("示例: python import_articles.py /mnt/c/Users/xxx/blog/source/_posts")
        sys.exit(1)
    
    directory = sys.argv[1]
    
    if not os.path.exists(directory):
        print(f"❌ 目录不存在: {directory}")
        sys.exit(1)
    
    # 扫描 Markdown 文件
    md_files = scan_markdown_files(directory)
    
    if not md_files:
        print(f"❌ 目录中没有找到 .md 文件: {directory}")
        sys.exit(1)
    
    print(f"📋 找到 {len(md_files)} 个 Markdown 文件")
    
    # 预览前 5 篇文章的元数据
    print("\n📝 文章元数据预览：")
    for file_path in md_files[:5]:
        article = read_markdown_file(file_path)
        categories_str = "/".join(article.get("categories", []))
        print(f"   • {article['title']}")
        if categories_str:
            print(f"     分类: [{categories_str}]")
    if len(md_files) > 5:
        print(f"   ... 还有 {len(md_files) - 5} 个文件")
    
    # 确认导入
    print(f"\n⚠️  即将导入 {len(md_files)} 篇文章到知识库")
    print("   这会调用 DashScope API 生成向量（会产生少量费用）")
    confirm = input("确认导入？(y/N): ").strip().lower()
    
    if confirm != 'y':
        print("❌ 取消导入")
        return
    
    # 获取 Token
    token = get_token()
    
    # 导入文章
    print(f"\n🔄 正在导入...")
    success_count = 0
    
    for i, file_path in enumerate(md_files, 1):
        print(f"\n[{i}/{len(md_files)}] 导入中...")
        
        try:
            article = read_markdown_file(file_path)
            if import_article(token, article):
                success_count += 1
        except Exception as e:
            print(f"   ❌ {os.path.basename(file_path)}: {str(e)}")
    
    print(f"\n✅ 导入完成: {success_count}/{len(md_files)} 篇文章")


if __name__ == "__main__":
    main()
