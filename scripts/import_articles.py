#!/usr/bin/env python3
"""
批量导入文章脚本（增量版）

支持：
- 增量导入：只导入新文章
- 更新检测：检测文章内容是否修改，如果修改则重新向量化
- 强制重新导入：--force 参数
- 清除所有文章：--clear 参数
"""
import os
import re
import sys
import yaml
import json
import hashlib
import requests
from pathlib import Path
from typing import List, Dict, Any

API_BASE = "http://localhost:8001"


def get_token() -> str:
    """获取匿名 Token"""
    response = requests.post(f"{API_BASE}/api/auth/anonymous")
    return response.json()["token"]


def parse_frontmatter(content: str) -> Dict[str, Any]:
    """解析 front-matter"""
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
    """标准化 categories 格式"""
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
    """标准化 tags 格式"""
    if not tags:
        return []
    
    if isinstance(tags, str):
        return [tags]
    
    if isinstance(tags, list):
        return [str(tag) for tag in tags]
    
    return []


def read_markdown_file(file_path: str) -> Dict:
    """读取 Markdown 文件（带 front-matter 解析）"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    frontmatter = parse_frontmatter(content)
    
    title = frontmatter.get("title")
    if not title:
        title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
        else:
            title = Path(file_path).stem
    
    categories = normalize_categories(frontmatter.get("categories"))
    tags = normalize_tags(frontmatter.get("tags"))
    
    posts_marker = "_posts/"
    posts_index = file_path.find(posts_marker)
    if posts_index != -1:
        relative_path = file_path[posts_index + len(posts_marker):]
    else:
        relative_path = os.path.basename(file_path)
    
    if relative_path.endswith(".md"):
        relative_path = relative_path[:-3]
    
    # 计算内容 hash（用于检测修改）
    content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
    
    return {
        "title": title,
        "content": content,
        "url": f"file://{os.path.abspath(file_path)}",
        "source": "blog",
        "categories": categories,
        "tags": tags,
        "relative_path": relative_path,
        "author": frontmatter.get("author", ""),
        "date": str(frontmatter.get("date", "")),
        "content_hash": content_hash
    }


def scan_markdown_files(directory: str) -> List[str]:
    """扫描目录下的 Markdown 文件"""
    md_files = []
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".md"):
                md_files.append(os.path.join(root, file))
    
    return sorted(md_files)


def get_existing_articles(token: str) -> Dict[str, Dict]:
    """获取知识库中已存在的文章（返回 {url: {id, title}} 字典）"""
    headers = {"Authorization": f"Bearer {token}"}
    all_articles = []
    skip = 0
    limit = 100  # 每次获取 100 篇
    
    while True:
        response = requests.get(
            f"{API_BASE}/api/knowledge/articles",
            headers=headers,
            params={"skip": skip, "limit": limit}
        )
        
        if response.status_code != 200:
            print(f"❌ 获取文章列表失败: {response.text[:100]}")
            break
        
        articles = response.json()
        if not articles:
            break
        
        all_articles.extend(articles)
        skip += limit
        
        # 如果返回的文章数少于 limit，说明已经是最后一页
        if len(articles) < limit:
            break
    
    return {a["url"]: a for a in all_articles if a.get("url")}


def delete_article(token: str, article_id: str) -> bool:
    """删除文章"""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.delete(f"{API_BASE}/api/knowledge/articles/{article_id}", headers=headers)
    return response.status_code == 200


def clear_all_articles(token: str) -> int:
    """清除所有文章，返回删除数量"""
    headers = {"Authorization": f"Bearer {token}"}
    all_articles = []
    skip = 0
    limit = 100
    
    while True:
        response = requests.get(
            f"{API_BASE}/api/knowledge/articles",
            headers=headers,
            params={"skip": skip, "limit": limit}
        )
        if response.status_code != 200:
            break
        articles = response.json()
        if not articles:
            break
        all_articles.extend(articles)
        skip += limit
        if len(articles) < limit:
            break
    
    deleted = 0
    for article in all_articles:
        article_id = article.get("id")
        if article_id:
            if delete_article(token, article_id):
                deleted += 1
    
    return deleted


def import_article(token: str, article: Dict) -> bool:
    """导入单篇文章"""
    request_data = {
        "title": article["title"],
        "url": article["url"],
        "content": article["content"],
        "source": article["source"],
        "date": article.get("date", ""),
        "categories": article.get("categories", []),
        "tags": article.get("tags", [])
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


def main():
    # 解析命令行参数
    args = sys.argv[1:]
    
    # 检查特殊参数
    clear_mode = "--clear" in args
    force_mode = "--force" in args
    help_mode = "--help" in args or "-h" in args
    
    # 移除特殊参数
    args = [a for a in args if not a.startswith("--") and not a.startswith("-")]
    
    if help_mode:
        print("📚 批量导入文章脚本（增量版）")
        print("=" * 50)
        print("用法:")
        print("  python import_articles.py <文章目录>")
        print("  python import_articles.py <文章目录> --force")
        print("  python import_articles.py --clear")
        print("")
        print("参数:")
        print("  <文章目录>  包含 .md 文件的目录")
        print("  --force     强制重新导入所有文章（覆盖已有）")
        print("  --clear     清除知识库中的所有文章")
        print("  -h, --help  显示帮助信息")
        print("")
        print("示例:")
        print("  python import_articles.py /mnt/c/Users/xxx/blog/source/_posts")
        print("  python import_articles.py /mnt/c/Users/xxx/blog/source/_posts --force")
        print("  python import_articles.py --clear")
        return
    
    # 清除模式
    if clear_mode:
        print("🗑️  清除知识库中的所有文章")
        print("=" * 50)
        confirm = input("⚠️  确认清除所有文章？(y/N): ").strip().lower()
        
        if confirm != 'y':
            print("❌ 取消清除")
            return
        
        token = get_token()
        deleted = clear_all_articles(token)
        print(f"\n✅ 清除完成: 删除了 {deleted} 篇文章")
        return
    
    # 导入模式
    if not args:
        print("❌ 请提供文章目录")
        print("用法: python import_articles.py <文章目录>")
        print("帮助: python import_articles.py --help")
        sys.exit(1)
    
    directory = args[0]
    
    if not os.path.exists(directory):
        print(f"❌ 目录不存在: {directory}")
        sys.exit(1)
    
    # 扫描 Markdown 文件
    md_files = scan_markdown_files(directory)
    
    if not md_files:
        print(f"❌ 目录中没有找到 .md 文件: {directory}")
        sys.exit(1)
    
    print(f"📚 批量导入文章到知识库（增量版）")
    print("=" * 50)
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
    
    # 获取 Token
    token = get_token()
    
    # 获取已存在的文章
    print("\n🔍 检查已存在的文章...")
    existing_articles = get_existing_articles(token)
    print(f"   知识库中已有 {len(existing_articles)} 篇文章")
    
    # 分析需要导入的文章
    new_articles = []
    updated_articles = []
    skipped_articles = []
    
    for file_path in md_files:
        article = read_markdown_file(file_path)
        url = article["url"]
        
        if url in existing_articles:
            existing = existing_articles[url]
            # 检查内容是否修改（通过比较标题，因为 content_hash 不在 API 返回中）
            if existing.get("title") != article["title"]:
                updated_articles.append((file_path, article, existing["id"]))
            else:
                skipped_articles.append(file_path)
        else:
            new_articles.append((file_path, article))
    
    # 显示分析结果
    print(f"\n📊 分析结果：")
    print(f"   📄 新文章: {len(new_articles)} 篇")
    print(f"   🔄 需更新: {len(updated_articles)} 篇")
    print(f"   ⏭️  已存在: {len(skipped_articles)} 篇")
    
    # 强制模式：把所有已存在的文章都加入更新列表
    if force_mode:
        print("\n⚡ 强制模式：将清除并重新导入所有文章")
        updated_articles = [(fp, art, existing_articles[art["url"]]["id"]) 
                           for fp, art in [(f, read_markdown_file(f)) for f in md_files]
                           if art["url"] in existing_articles]
        # 新文章不需要了，全部走更新流程
        new_articles = [(fp, art) for fp, art in new_articles if art["url"] not in existing_articles]
    
    if not new_articles and not updated_articles:
        print("\n✅ 所有文章都已是最新状态，无需导入")
        return
    
    # 确认导入
    if force_mode:
        confirm = "y"
    else:
        print(f"\n⚠️  即将导入/更新 {len(new_articles) + len(updated_articles)} 篇文章")
        print("   这会调用 DashScope API 生成向量（会产生少量费用）")
        confirm = input("确认导入？(y/N): ").strip().lower()
    
    if confirm != 'y':
        print("❌ 取消导入")
        return
    
    # 导入新文章
    success_count = 0
    
    if new_articles:
        print(f"\n📄 导入新文章...")
        for i, (file_path, article) in enumerate(new_articles, 1):
            print(f"\n[{i}/{len(new_articles)}] 导入中...")
            try:
                if import_article(token, article):
                    success_count += 1
            except Exception as e:
                print(f"   ❌ {os.path.basename(file_path)}: {str(e)}")
    
    # 更新已修改的文章（或强制重新导入）
    if updated_articles:
        print(f"\n🔄 {'重新导入' if force_mode else '更新已修改'}文章...")
        for i, (file_path, article, article_id) in enumerate(updated_articles, 1):
            print(f"\n[{i}/{len(updated_articles)}] {'重新导入' if force_mode else '更新'}中...")
            try:
                delete_article(token, article_id)
                if import_article(token, article):
                    success_count += 1
            except Exception as e:
                print(f"   ❌ {os.path.basename(file_path)}: {str(e)}")
    
    # 强制模式：重新导入所有文章
    if force_mode and updated_articles:
        print(f"\n⚡ 强制重新导入...")
        for i, (file_path, article, article_id) in enumerate(updated_articles, 1):
            print(f"\n[{i}/{len(updated_articles)}] 重新导入中...")
            try:
                # 先删除旧文章
                delete_article(token, article_id)
                # 再导入新文章
                if import_article(token, article):
                    success_count += 1
            except Exception as e:
                print(f"   ❌ {os.path.basename(file_path)}: {str(e)}")
    
    print(f"\n✅ 导入完成: {success_count}/{len(new_articles) + len(updated_articles)} 篇文章")


if __name__ == "__main__":
    main()
