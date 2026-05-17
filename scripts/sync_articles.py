#!/usr/bin/env python3
"""
博文向量化增量同步脚本

以 front-matter date 为文章唯一标识，对比本地 .sync_record.json
检测新增/修改的文章 → embedding → 插入/更新 PostgreSQL。
不受文件移动影响，因为 date 是稳定字段。

用法:
  python scripts/sync_articles.py              # 增量同步
  python scripts/sync_articles.py --force       # 全量重导
  python scripts/sync_articles.py --dry-run     # 仅预览变更，不实际导入

配置:
  读取 agent-service/.env 中的 BLOG_BASE_URL、DATABASE_URL、DASHSCOPE_API_KEY
  以及 BLOG_ARTICLES_DIR（文章父级目录）
"""
import os
import re
import sys
import json
import yaml
import hashlib
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# ── 加载 .env ──
def load_env(env_path: str) -> Dict[str, str]:
    """读取 .env 文件，返回键值对字典"""
    env = {}
    if not os.path.exists(env_path):
        return env
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip().strip('"').strip("'")
    return env


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
ENV_FILE = PROJECT_DIR / "agent-service" / ".env"
env = load_env(str(ENV_FILE))

# ── 配置 ──
BLOG_ARTICLES_DIR = env.get("BLOG_ARTICLES_DIR", "")
BLOG_BASE_URL = env.get("BLOG_BASE_URL", "https://xn--ljhfjm-dl0o.top")
DATABASE_URL = env.get("DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost:5432/hexo_agent")
DASHSCOPE_API_KEY = env.get("DASHSCOPE_API_KEY", "")

SYNC_RECORD_FILE = "sync_record.json"  # 放在文章目录下

# ── Front-matter 解析 ──
def parse_frontmatter(content: str) -> Dict[str, Any]:
    """解析 YAML front-matter"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def normalize_categories(cats: Any) -> List[str]:
    if not cats:
        return []
    if isinstance(cats, str):
        return [cats]
    if isinstance(cats, list):
        result = []
        for item in cats:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, list):
                result.extend([str(i) for i in item])
        return result
    return []


def normalize_tags(tags: Any) -> List[str]:
    if not tags:
        return []
    if isinstance(tags, str):
        return [tags.lower()]
    if isinstance(tags, list):
        return [str(t).lower() for t in tags]
    return []


# ── 文章扫描 ──
def scan_articles(articles_dir: str) -> List[Dict]:
    """扫描目录下所有 .md 文件，提取 front-matter + 内容 hash"""
    articles = []
    for root, _, files in os.walk(articles_dir):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            filepath = os.path.join(root, fname)
            with open(filepath, encoding="utf-8") as f:
                content = f.read()

            fm = parse_frontmatter(content)
            date_str = str(fm.get("date", ""))
            title = fm.get("title") or Path(fname).stem
            categories = normalize_categories(fm.get("categories"))
            tags = normalize_tags(fm.get("tags"))
            content_hash = hashlib.md5(content.encode()).hexdigest()

            # key = date + 文件路径 hash（避免同日期文章冲突）
            path_hash = hashlib.md5(filepath.encode()).hexdigest()[:8]
            stable_key = f"{date_str}_{path_hash}" if date_str else f"nodate:{Path(fname).stem}_{path_hash}"

            articles.append({
                "key": stable_key,
                "title": title,
                "file": filepath,
                "content": content,
                "date": date_str,
                "categories": categories,
                "tags": tags,
                "hash": content_hash,
                "permalink": fm.get("permalink") or fm.get("url"),
                "abbrlink": fm.get("abbrlink"),
            })

    # 按 front-matter date 排序（date 缺失的排最后）
    articles.sort(key=lambda a: a.get("date") or "9999")
    return articles


# ── 同步记录管理 ──
def load_sync_record(articles_dir: str) -> Dict[str, Dict]:
    """加载本地同步记录文件 .sync_record.json"""
    record_path = os.path.join(articles_dir, SYNC_RECORD_FILE)
    if os.path.exists(record_path):
        with open(record_path) as f:
            return json.load(f)
    return {}


def save_sync_record(articles_dir: str, record: Dict[str, Dict]):
    """保存同步记录"""
    record_path = os.path.join(articles_dir, SYNC_RECORD_FILE)
    with open(record_path, "w") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def detect_changes(articles: List[Dict], prev_record: Dict[str, Dict]):
    """对比本地文章和上次同步记录，返回 (新增, 修改)"""
    added, modified = [], []
    for art in articles:
        key = art["key"]
        if key not in prev_record:
            added.append(art)
        elif prev_record[key].get("hash") != art["hash"]:
            modified.append(art)
    return added, modified


# ── URL 构建 ──
def build_blog_url(article: Dict) -> str:
    """构造博客文章 URL（与 import_articles.py 保持一致）"""
    permalink = article.get("permalink")
    if permalink:
        return BLOG_BASE_URL.rstrip("/") + "/" + str(permalink).strip("/")
    abbrlink = article.get("abbrlink")
    if abbrlink:
        return f"{BLOG_BASE_URL.rstrip('/')}/{abbrlink}"
    date_str = article.get("date", "")
    rel = os.path.relpath(article["file"], BLOG_ARTICLES_DIR)
    posts_idx = article["file"].find("_posts/")
    if posts_idx != -1:
        post_path = article["file"][posts_idx + len("_posts/"):]
    else:
        post_path = Path(article["file"]).stem
    if post_path.endswith(".md"):
        post_path = post_path[:-3]
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return f"{BLOG_BASE_URL.rstrip('/')}/{dt.strftime('%Y/%m/%d')}/{post_path}/"
        except Exception:
            pass
    return f"{BLOG_BASE_URL.rstrip('/')}/{post_path}/"


# ── 核心同步逻辑 ──
async def sync_articles(force: bool = False, dry_run: bool = False):
    """主同步流程"""
    print("📚 Hexo 博文增量同步")
    print(f"   目录: {BLOG_ARTICLES_DIR}")
    print(f"   博客: {BLOG_BASE_URL}")
    print(f"   DB:   {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")
    print()

    if not BLOG_ARTICLES_DIR or not os.path.isdir(BLOG_ARTICLES_DIR):
        print(f"❌ 文章目录不存在: {BLOG_ARTICLES_DIR}")
        print("   请在 .env 中设置 BLOG_ARTICLES_DIR")
        sys.exit(1)

    # 1. 扫描文章
    articles = scan_articles(BLOG_ARTICLES_DIR)
    print(f"📋 扫描到 {len(articles)} 篇文章")

    # 2. 对比
    prev_record = load_sync_record(BLOG_ARTICLES_DIR)
    added, modified = detect_changes(articles, prev_record)

    if force:
        added = articles
        modified = []
        print("⚡ 强制模式：全量重导")

    print(f"   📄 新增: {len(added)}   🔄 修改: {len(modified)}   ⏭️ 跳过: {len(articles) - len(added) - len(modified)}")

    if not added and not modified:
        print("✅ 所有文章已是最新状态")
        return

    if dry_run:
        print("\n🔍 预览变更（dry-run）：")
        for a in added:
            print(f"   + {a['title'][:40]}  date={a['date']}")
        for a in modified:
            print(f"   ~ {a['title'][:40]}  date={a['date']}")
        return

    # 3. 导入数据库（复用项目内模块）
    sys.path.insert(0, str(PROJECT_DIR / "agent-service"))
    os.chdir(PROJECT_DIR / "agent-service")

    from app.config import settings as app_settings
    from app.core.database import async_session_maker
    from app.knowledge.chunker import chunk_markdown
    from app.knowledge.embedder import embedding_service
    from app.models.knowledge import Article, Chunk
    from sqlalchemy import select, delete as sa_delete

    app_settings.DASHSCOPE_API_KEY = DASHSCOPE_API_KEY

    success, fail = 0, 0
    to_process = added + modified

    async with async_session_maker() as db:
        for i, art in enumerate(to_process):
            url = build_blog_url(art)
            is_new = art in added
            label = "新增" if is_new else "修改"
            print(f"\n[{i+1}/{len(to_process)}] {label}: {art['title'][:40]}")

            try:
                # 剥离 front-matter
                body = re.sub(r'^---\s*\n.*?\n---\s*\n', '', art["content"], flags=re.DOTALL)
                chunks = chunk_markdown(body, file_path=url)
                texts = [c["content"] for c in chunks]
                embeddings = await embedding_service.embed_batch(texts)

                # 检查已有文章
                result = await db.execute(select(Article).where(Article.url == url))
                existing = result.scalar_one_or_none()

                if existing:
                    await db.execute(sa_delete(Chunk).where(Chunk.article_id == existing.id))
                    existing.title = art["title"]
                    existing.content = art["content"]
                    existing.synced_at = datetime.utcnow()
                else:
                    article = Article(
                        title=art["title"], url=url, content=art["content"],
                        source="blog", synced_at=datetime.utcnow(),
                    )
                    db.add(article)
                    await db.flush()

                for cdata, emb in zip(chunks, embeddings):
                    meta = cdata["metadata"]
                    meta["categories"] = art["categories"]
                    meta["tags"] = art["tags"]
                    meta["title"] = art["title"]
                    db.add(Chunk(
                        article_id=existing.id if existing else article.id,
                        chunk_index=meta["chunk_index"],
                        content=cdata["content"],
                        embedding=emb,
                        metadata_=meta,
                    ))

                await db.commit()
                print(f"   ✅ {len(chunks)} chunks")
                success += 1

                # 更新记录
                prev_record[art["key"]] = {
                    "title": art["title"],
                    "hash": art["hash"],
                    "url": url,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            except Exception as e:
                await db.rollback()
                print(f"   ❌ {e}")
                fail += 1

    # 4. 保存同步记录
    save_sync_record(BLOG_ARTICLES_DIR, prev_record)

    print(f"\n✅ 同步完成: 成功 {success}, 失败 {fail}")
    print(f"   记录已保存: {BLOG_ARTICLES_DIR}/{SYNC_RECORD_FILE}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--") or a == "--force" or a == "--dry-run"]
    force = "--force" in sys.argv
    dry = "--dry-run" in sys.argv

    if not BLOG_ARTICLES_DIR:
        print("❌ 请在 agent-service/.env 中设置 BLOG_ARTICLES_DIR=你的文章父级目录")
        sys.exit(1)

    asyncio.run(sync_articles(force=force, dry_run=dry))
