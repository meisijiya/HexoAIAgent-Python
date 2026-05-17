#!/bin/bash
# ===============================================================
# Hexo Agent Widget 构建脚本
# 将 API_BASE 从 .env 注入 Widget JS + 生成版本哈希
# 用法: bash scripts/sync-widget.sh
# 
# 注：博客直接从服务器加载 Widget，无需拷贝到 Hexo 目录
# ===============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

SRC_JS="$PROJECT_DIR/agent-service/app/static/agent-widget.js"
WIDGET_JS="$PROJECT_DIR/hexo-widget/source/js/agent-widget.js"
VERSION_FILE="$PROJECT_DIR/hexo-widget/version.json"

ENV_FILE="$PROJECT_DIR/agent-service/.env"
if [ -f "$ENV_FILE" ]; then
    API_BASE=$(grep -oP '^API_BASE=\K.*' "$ENV_FILE" | tr -d '"' | tr -d "'")
fi
API_BASE="${API_BASE:-http://localhost:8001}"

echo "📦 Hexo Agent Widget 构建"
echo "   API_BASE: $API_BASE"
echo "========================="

# 注：用临时文件 + mv 避免 sed -i 处理特殊字符问题
sed "s|__API_BASE__|$API_BASE|g" "$SRC_JS" > "$SRC_JS.tmp" && mv "$SRC_JS.tmp" "$SRC_JS"
echo "✅ 服务端 Widget → $API_BASE"

sed "s|__API_BASE__|$API_BASE|g" "$WIDGET_JS" > "$WIDGET_JS.tmp" && mv "$WIDGET_JS.tmp" "$WIDGET_JS"
echo "✅ NPM 包 Widget → $API_BASE"

WIDGET_HASH=$(sha256sum "$SRC_JS" | cut -c1-12)
echo "{\"hash\": \"$WIDGET_HASH\", \"synced_at\": \"$(date -Iseconds)\"}" > "$VERSION_FILE"
echo "✅ 版本 Hash: $WIDGET_HASH"

echo ""
echo "🎉 构建完成！Docker 重建后生效"
