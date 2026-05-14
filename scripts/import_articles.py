#!/usr/bin/env python3
"""
批量导入文章脚本

支持从 Markdown 文件夹导入文章到知识库
"""
import os
import re
import requests
import sys
from pathlib import Path
from typing import List, Dict

API_BASE = "http://localhost:8001"


def get_token() -> str:
    """获取匿名 Token"""
    response = requests.post(f"{API_BASE}/api/auth/anonymous")
    return response.json()["token"]


def read_markdown_file(file_path: str) -> Dict:
    """
    读取 Markdown 文件
    
    Args:
        file_path: 文件路径
    
    Returns:
        Dict: 包含标题和内容的字典
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取标题（第一个 # 标题或文件名）
    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
    else:
        title = Path(file_path).stem
    
    return {
        "title": title,
        "content": content,
        "url": f"file://{os.path.abspath(file_path)}",
        "source": "blog"
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
    response = requests.post(
        f"{API_BASE}/api/knowledge/articles",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        },
        json=article
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"   ✅ {article['title']} ({result['chunks_count']} 个分块)")
        return True
    else:
        print(f"   ❌ {article['title']}: {response.text}")
        return False


def scan_markdown_files(directory: str) -> List[str]:
    """
    扫描目录下的 Markdown 文件
    
    Args:
        directory: 目录路径
    
    Returns:
        List[str]: 文件路径列表
    """
    md_files = []
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.md'):
                md_files.append(os.path.join(root, file))
    
    return sorted(md_files)


def main():
    print("📚 批量导入文章到知识库")
    print("=" * 50)
    
    # 检查参数
    if len(sys.argv) < 2:
        print("用法: python import_articles.py <文章目录>")
        print("示例: python import_articles.py ./my-blog/source/_posts")
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
    
    print(f"📋 找到 {len(md_files)} 个 Markdown 文件：")
    for file in md_files[:5]:
        print(f"   - {os.path.basename(file)}")
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
        print(f"[{i}/{len(md_files)}] 导入中...")
        
        try:
            article = read_markdown_file(file_path)
            if import_article(token, article):
                success_count += 1
        except Exception as e:
            print(f"   ❌ {os.path.basename(file_path)}: {str(e)}")
    
    print(f"\n✅ 导入完成: {success_count}/{len(md_files)} 篇文章")
    print(f"   总分块数需要通过 API 查询")


if __name__ == "__main__":
    main()
