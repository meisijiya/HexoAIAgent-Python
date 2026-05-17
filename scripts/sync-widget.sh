#!/bin/bash
# ===============================================================
# Hexo Agent Widget 同步脚本
# 将前端代码同步到 Hexo 主题 + hexo-widget 源码目录
# 用法: bash scripts/sync-widget.sh
# ===============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

SRC_JS="$PROJECT_DIR/agent-service/app/static/agent-widget.js"
SRC_CSS="$PROJECT_DIR/agent-service/app/static/agent-widget.css"

# Hexo 博客主题路径（从 .env 读取，避免硬编码敏感路径）
ENV_FILE="$PROJECT_DIR/agent-service/.env"
if [ -f "$ENV_FILE" ]; then
    HEXO_THEME_DIR=$(grep -oP 'HEXO_THEME_PATH=\K.*' "$ENV_FILE" | tr -d '"' | tr -d "'")
fi
HEXO_THEME_DIR="${HEXO_THEME_DIR:-/mnt/c/Users/22923/Desktop/blog/themes/Chic}"

HEXO_THEME_JS="$HEXO_THEME_DIR/source/js/agent-widget.js"
HEXO_THEME_CSS="$HEXO_THEME_DIR/source/css/agent-widget.css"

# hexo-widget NPM 包源码
WIDGET_JS="$PROJECT_DIR/hexo-widget/source/js/agent-widget.js"
WIDGET_CSS="$PROJECT_DIR/hexo-widget/source/css/agent-widget.css"

# 版本缓存文件
VERSION_FILE="$PROJECT_DIR/hexo-widget/version.json"

echo "📦 Hexo Agent Widget 同步"
echo "   Hexo 主题: $HEXO_THEME_DIR"
echo "========================="

if [ ! -f "$SRC_JS" ]; then
    echo "❌ 源文件不存在: $SRC_JS"
    exit 1
fi

cp "$SRC_JS" "$HEXO_THEME_JS" && echo "✅ JS → Chic 主题"
cp "$SRC_CSS" "$HEXO_THEME_CSS" && echo "✅ CSS → Chic 主题"
cp "$SRC_JS" "$WIDGET_JS" && echo "✅ JS → hexo-widget"
cp "$SRC_CSS" "$WIDGET_CSS" && echo "✅ CSS → hexo-widget"

# 生成 JS 内容哈希（浏览器缓存版本控制：内容不变→hash不变→浏览器用缓存）
WIDGET_HASH=$(sha256sum "$SRC_JS" | cut -c1-12)
echo "{\"hash\": \"$WIDGET_HASH\", \"synced_at\": \"$(date -Iseconds)\"}" > "$VERSION_FILE"
echo "✅ 版本 Hash: $WIDGET_HASH → hexo-widget/version.json"

echo ""
echo "🎉 同步完成！刷新 http://localhost:4000 测试"
