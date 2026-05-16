#!/bin/bash
# 博客知识库自动同步脚本
# 
# 功能：从 GitHub 拉取博客源文件，增量导入知识库
# 用法：./sync-knowledge.sh
# 定时：crontab -e → */5 * * * * /path/to/sync-knowledge.sh

set -e

# ==================== 配置 ====================
REPO_URL="https://github.com/meisijiya/Blog.git"
REPO_BRANCH="master"
SYNC_DIR="/tmp/blog-source"
POSTS_DIR="$SYNC_DIR/source/_posts"
SCRIPTS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$SCRIPTS_DIR/sync/sync.log"
LOCK_FILE="/tmp/blog-sync.lock"

# ==================== 函数 ====================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

cleanup() {
    rm -f "$LOCK_FILE"
}

# ==================== 检查锁 ====================

if [ -f "$LOCK_FILE" ]; then
    # 检查锁是否超过 10 分钟
    lock_age=$(( $(date +%s) - $(stat -c %Y "$LOCK_FILE" 2>/dev/null || echo 0) ))
    if [ "$lock_age" -lt 600 ]; then
        log "已有同步任务在运行，跳过"
        exit 0
    else
        log "锁文件过期，清理"
        rm -f "$LOCK_FILE"
    fi
fi

trap cleanup EXIT
touch "$LOCK_FILE"

# ==================== 拉取更新 ====================

log "开始同步..."

if [ -d "$SYNC_DIR/.git" ]; then
    # 已有仓库，拉取更新
    cd "$SYNC_DIR"
    OLD_COMMIT=$(git rev-parse HEAD)
    git fetch origin "$REPO_BRANCH" --quiet
    git reset --hard "origin/$REPO_BRANCH" --quiet
    NEW_COMMIT=$(git rev-parse HEAD)
    
    if [ "$OLD_COMMIT" = "$NEW_COMMIT" ]; then
        log "无新提交，跳过"
        exit 0
    fi
    
    # 检查是否有文章变更
    CHANGED_FILES=$(git diff --name-only "$OLD_COMMIT" "$NEW_COMMIT" | grep "source/_posts/.*\.md$" || true)
    if [ -z "$CHANGED_FILES" ]; then
        log "无文章变更，跳过"
        exit 0
    fi
    
    log "检测到文章变更："
    echo "$CHANGED_FILES" | while read f; do log "  - $f"; done
else
    # 首次克隆
    log "首次克隆仓库..."
    git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$SYNC_DIR" --quiet
fi

# ==================== 增量导入 ====================

log "开始增量导入..."
cd "$SCRIPTS_DIR"
python3 import_articles.py "$POSTS_DIR" 2>&1 | tee -a "$LOG_FILE"

log "同步完成"
