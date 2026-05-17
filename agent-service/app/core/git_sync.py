"""
Git 轮询博文同步模块

定时从备用 GitHub 仓库拉取博文，检测新增/修改/删除的文章，并增量导入到知识库。
与 cleanup.py 的定时任务架构一致，使用 asyncio.sleep 实现定时循环。
"""
import asyncio
import hashlib
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import select, delete as sa_delete

from app.config import settings
from app.core.database import async_session_maker
from app.core.redis import get_redis
from app.knowledge.chunker import chunk_markdown
from app.knowledge.embedder import embedding_service
from app.knowledge.frontmatter_parser import (
    parse_frontmatter,
    normalize_categories,
    normalize_tags,
)
from app.models.knowledge import Article, Chunk, SyncLog


# Redis key 前缀
REDIS_KEY_LAST_COMMIT = "git_sync:last_commit"
REDIS_KEY_LAST_RUN = "git_sync:last_run_at"

# 默认轮询间隔（分钟），可通过环境变量 GIT_POLL_INTERVAL_MINUTES 覆盖
DEFAULT_POLL_INTERVAL_MINUTES = 30

# 备用仓库本地路径（Docker volume 挂载点）
LOCAL_REPO_PATH = "/data/blog-repo"


@dataclass
class SyncResult:
    """同步结果"""
    added: int = 0
    updated: int = 0
    deleted: int = 0
    errors: List[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    @property
    def total(self) -> int:
        return self.added + self.updated + self.deleted

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


class GitSyncManager:
    """
    Git 博文同步管理器

    工作流：
    1. clone 或 pull 备用 GitHub 仓库到本地
    2. 对比上次同步的 HEAD commit，检测变更文件
    3. 对新增/修改的 .md 文件：解析 front-matter → 分块 → embedding → 入库
    4. 对已删除的 .md 文件：从知识库中删除
    5. 记录同步状态到 Redis + SyncLog 表
    """

    def __init__(self, repo_url: str, posts_path: str = "source/_posts/"):
        self.repo_url = repo_url
        self.posts_path = posts_path.rstrip("/") + "/"
        self.repo_dir = Path(LOCAL_REPO_PATH)
        self.posts_dir = self.repo_dir / self.posts_path

    # ── Git 操作 ──

    def _run_git(self, *args: str, cwd: Optional[Path] = None) -> Tuple[int, str, str]:
        """执行 git 命令，返回 (returncode, stdout, stderr)"""
        cmd = ["git"] + list(args)
        proc = subprocess.run(
            cmd,
            cwd=str(cwd or self.repo_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def _ensure_repo(self) -> bool:
        """确保仓库存在：首次 clone，后续 pull"""
        if (self.repo_dir / ".git").exists():
            rc, stdout, stderr = self._run_git("pull", "origin", "main")
            if rc != 0:
                logger.error(f"Git pull 失败: {stderr}")
                return False
            logger.info(f"Git pull 成功: {stdout[:100] if stdout else '已是最新'}")
            return True
        else:
            self.repo_dir.mkdir(parents=True, exist_ok=True)
            rc, stdout, stderr = self._run_git(
                "clone", self.repo_url, str(self.repo_dir),
                cwd=Path("/data")
            )
            if rc != 0:
                logger.error(f"Git clone 失败: {stderr}")
                return False
            logger.info(f"Git clone 成功: {stdout[:100]}")
            return True

    def _get_current_commit(self) -> Optional[str]:
        """获取当前仓库 HEAD commit"""
        rc, stdout, _ = self._run_git("rev-parse", "HEAD")
        if rc == 0 and stdout:
            return stdout
        return None

    def _get_changed_files(self, last_commit: Optional[str]) -> Dict[str, List[str]]:
        """
        检测变更文件

        返回:
            {"added": [...], "modified": [...], "deleted": [...]}
        """
        result = {"added": [], "modified": [], "deleted": []}

        if last_commit:
            rc, stdout, stderr = self._run_git(
                "diff", "--name-status", f"{last_commit}..HEAD"
            )
            if rc != 0:
                logger.warning(f"Git diff 失败: {stderr}，回退到全量扫描")
                last_commit = None

        if last_commit is None:
            # 首次同步：全量扫描
            posts_dir = self.posts_dir
            if not posts_dir.exists():
                logger.warning(f"博文目录不存在: {posts_dir}")
                return result
            result["added"] = [
                str(p.relative_to(self.repo_dir))
                for p in sorted(posts_dir.rglob("*.md"))
            ]
            return result

        # 增量变更解析
        for line in stdout.split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            status, path = parts
            # 只关心 posts_path 下的 .md 文件
            if not path.startswith(self.posts_path) or not path.endswith(".md"):
                continue
            if status == "A":
                result["added"].append(path)
            elif status == "M":
                result["modified"].append(path)
            elif status == "D":
                result["deleted"].append(path)

        return result

    # ── 文章处理 ──

    def _read_article_file(self, relative_path: str) -> Optional[Dict]:
        """读取文章文件，返回 {title, content, url}"""
        filepath = self.repo_dir / relative_path
        if not filepath.exists():
            return None
        try:
            content = filepath.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"读取文件失败 {relative_path}: {e}")
            return None

        frontmatter = parse_frontmatter(content)
        title = frontmatter.get("title", filepath.stem)
        permalink = frontmatter.get("url") or frontmatter.get("permalink")
        if permalink:
            url = settings.BLOG_BASE_URL.rstrip("/") + "/" + str(permalink).strip("/")
        else:
            abbrlink = frontmatter.get("abbrlink")
            if abbrlink:
                url = f"{settings.BLOG_BASE_URL.rstrip('/')}/{abbrlink}"
            else:
                # 提取 _posts/ 下的相对路径（匹配 Hexo permalink :title）
                rel = str(relative_path)
                posts_idx = rel.find("_posts/")
                if posts_idx != -1:
                    post_path = rel[posts_idx + len("_posts/"):]
                else:
                    post_path = str(filepath.stem)
                if post_path.endswith(".md"):
                    post_path = post_path[:-3]
                date_str = str(frontmatter.get("date", ""))
                if date_str:
                    from datetime import datetime as dt_parse
                    try:
                        dt = dt_parse.fromisoformat(date_str.replace("Z", "+00:00"))
                        url = f"{settings.BLOG_BASE_URL.rstrip('/')}/{dt.strftime('%Y/%m/%d')}/{post_path}/"
                    except Exception:
                        url = f"{settings.BLOG_BASE_URL.rstrip('/')}/{post_path}/"
                else:
                    url = f"{settings.BLOG_BASE_URL.rstrip('/')}/{post_path}/"

        return {"title": title, "content": content, "url": url}

    async def _upsert_article(self, article_data: Dict, source_path: str) -> bool:
        """创建或更新文章（含分块+向量化）"""
        async with async_session_maker() as db:
            try:
                url = article_data["url"]
                title = article_data["title"]
                content = article_data["content"]

                # 解析 front-matter
                frontmatter = parse_frontmatter(content)
                categories = normalize_categories(frontmatter.get("categories"))
                tags = normalize_tags(frontmatter.get("tags"))

                # 检查是否已存在（URL 去重）
                existing = await db.execute(select(Article).where(Article.url == url))
                article = existing.scalar_one_or_none()

                if article:
                    # 更新已有文章：删除旧分块 → 重新创建
                    await db.execute(
                        sa_delete(Chunk).where(Chunk.article_id == article.id)
                    )
                    article.title = title
                    article.content = content
                    article.synced_at = datetime.now(timezone.utc)
                    action = "updated"
                else:
                    article = Article(
                        title=title,
                        url=url,
                        content=content,
                        source="blog",
                        synced_at=datetime.now(timezone.utc),
                    )
                    db.add(article)
                    await db.flush()
                    action = "added"

                # 剥离 front-matter 后再分块（避免 YAML 元数据被嵌入向量）
                body = re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, flags=re.DOTALL)
                chunks = chunk_markdown(body, file_path=url or title)
                texts = [c["content"] for c in chunks]
                embeddings = await embedding_service.embed_batch(texts)

                for chunk_data, embedding in zip(chunks, embeddings):
                    meta = chunk_data["metadata"]
                    meta["categories"] = categories
                    meta["tags"] = tags
                    meta["title"] = title

                    db.add(Chunk(
                        article_id=article.id,
                        chunk_index=meta["chunk_index"],
                        content=chunk_data["content"],
                        embedding=embedding,
                        metadata_=meta,
                    ))

                await db.commit()
                logger.info(f"文章{action}: {title} ({len(chunks)} chunks)")
                return True

            except Exception as e:
                await db.rollback()
                raise e

    async def _delete_article(self, relative_path: str) -> bool:
        """删除文章（通过文件路径反查 URL）"""
        slug = Path(relative_path).stem
        url = settings.BLOG_BASE_URL.rstrip("/") + "/" + slug

        async with async_session_maker() as db:
            result = await db.execute(select(Article).where(Article.url == url))
            article = result.scalar_one_or_none()
            if article:
                await db.delete(article)
                await db.commit()
                logger.info(f"文章已删除: {article.title}")
                return True
            return False

    # ── 主流程 ──

    async def sync_once(self) -> SyncResult:
        """执行一次完整同步"""
        result = SyncResult(started_at=datetime.now(timezone.utc))

        if not self.repo_url:
            result.errors.append("GIT_REPO_URL 未配置，跳过同步")
            return result

        # Step 1: 拉取最新代码
        if not self._ensure_repo():
            result.errors.append("Git 仓库操作失败")
            return result

        # Step 2: 获取旧 commit
        redis = get_redis()
        last_commit = None
        if redis:
            stored = await redis.get(REDIS_KEY_LAST_COMMIT)
            if stored:
                last_commit = stored.decode() if isinstance(stored, bytes) else stored

        # Step 3: 检测变更
        changes = self._get_changed_files(last_commit)

        if not any(changes.values()):
            logger.info("无文章变更，跳过同步")
            result.finished_at = datetime.now(timezone.utc)
            return result

        # Step 4: 处理新增 + 修改
        for filepath in changes["added"] + changes["modified"]:
            article_data = self._read_article_file(filepath)
            if article_data is None:
                result.errors.append(f"读取失败: {filepath}")
                continue
            try:
                await self._upsert_article(article_data, filepath)
                if filepath in changes["added"]:
                    result.added += 1
                else:
                    result.updated += 1
            except Exception as e:
                msg = f"处理失败 {filepath}: {e}"
                logger.error(msg)
                result.errors.append(msg)

        # Step 5: 处理删除
        for filepath in changes["deleted"]:
            try:
                if await self._delete_article(filepath):
                    result.deleted += 1
            except Exception as e:
                msg = f"删除失败 {filepath}: {e}"
                logger.error(msg)
                result.errors.append(msg)

        # Step 6: 更新同步状态
        current_commit = self._get_current_commit()
        if redis and current_commit:
            await redis.set(REDIS_KEY_LAST_COMMIT, current_commit)
            await redis.set(
                REDIS_KEY_LAST_RUN,
                datetime.now(timezone.utc).isoformat()
            )

        # Step 7: 记录 SyncLog
        async with async_session_maker() as db:
            db.add(SyncLog(
                added=result.added,
                updated=result.updated,
                deleted=result.deleted,
                errors=len(result.errors),
                message="; ".join(result.errors[:3]) if result.errors else "OK",
            ))
            await db.commit()

        result.finished_at = datetime.now(timezone.utc)
        duration = (result.finished_at - result.started_at).total_seconds()
        logger.info(
            f"Git 同步完成: +{result.added} ~{result.updated} -{result.deleted} "
            f"错误:{len(result.errors)} 耗时:{duration:.1f}s"
        )
        return result


# ── 全局实例 ──

_git_sync_manager: Optional[GitSyncManager] = None


def get_git_sync_manager() -> Optional[GitSyncManager]:
    """获取 GitSyncManager 单例（配置缺失时返回 None）"""
    global _git_sync_manager
    if _git_sync_manager is None:
        repo_url = getattr(settings, "GIT_REPO_URL", None)
        posts_path = getattr(settings, "GIT_POSTS_PATH", "source/_posts/")
        if repo_url:
            _git_sync_manager = GitSyncManager(repo_url, posts_path)
        else:
            logger.warning("GIT_REPO_URL 未配置，Git 同步功能禁用")
    return _git_sync_manager


async def _git_sync_loop():
    """
    Git 同步后台循环

    启动后立即执行一次初始同步，之后按 GIT_POLL_INTERVAL_MINUTES 间隔轮询
    """
    sync_mgr = get_git_sync_manager()
    if sync_mgr is None:
        logger.info("Git 同步未配置，跳过")
        return

    interval = int(getattr(settings, "GIT_POLL_INTERVAL_MINUTES", DEFAULT_POLL_INTERVAL_MINUTES))
    interval_seconds = interval * 60

    logger.info(f"Git 同步已启动（间隔: {interval} 分钟）")

    # 首次立即执行
    try:
        await sync_mgr.sync_once()
    except Exception as e:
        logger.error(f"初始 Git 同步失败: {e}")

    # 定时循环
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await sync_mgr.sync_once()
        except Exception as e:
            logger.error(f"Git 同步失败: {e}")
