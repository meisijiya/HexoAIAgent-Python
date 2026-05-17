#!/bin/bash
# ===============================================================
# Hexo Agent 交互式运维脚手架
# 用法: bash scripts/agent.sh
# 
# 自动检测环境：
#   - 本地有 Docker → 直接执行 Docker 命令
#   - 本地无 Docker → SSH 到服务器执行（需配置 SERVER_HOST）
# ===============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ── 环境检测 ──
ENV_FILE="$PROJECT_DIR/agent-service/.env"
SERVER_HOST=$(grep -oP 'SERVER_HOST=\K.*' "$ENV_FILE" 2>/dev/null | tr -d '"' | tr -d "'" || echo "")
SERVER_USER=$(grep -oP 'SERVER_USER=\K.*' "$ENV_FILE" 2>/dev/null | tr -d '"' | tr -d "'" || echo "root")
SERVER_PROJECT=$(grep -oP 'SERVER_PROJECT_PATH=\K.*' "$ENV_FILE" 2>/dev/null | tr -d '"' | tr -d "'" || echo "/opt/hexo-agent")

HAS_DOCKER=$(docker info &>/dev/null && echo "yes" || echo "no")

if [ "$HAS_DOCKER" == "yes" ]; then
    MODE="本地"
    REMOTE_PREFIX=""
else
    MODE="远程"
    if [ -z "$SERVER_HOST" ]; then
        echo -e "${RED}❌ 本地无 Docker 且未配置 SERVER_HOST（agent-service/.env）${NC}"
        echo "   请在 .env 中添加: SERVER_HOST=你的服务器IP"
        exit 1
    fi
    REMOTE_PREFIX="ssh $SERVER_USER@$SERVER_HOST"
fi

# ── 辅助函数 ──
banner() {
    clear
    echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║       🤖 Hexo Agent 运维脚手架           ║${NC}"
    echo -e "${CYAN}╠══════════════════════════════════════════╣${NC}"
    if [ "$MODE" == "远程" ]; then
        echo -e "${CYAN}║  🌐 远程模式 → $SERVER_USER@$SERVER_HOST${NC}"
    else
        echo -e "${CYAN}║  💻 本地模式${NC}"
    fi
    echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
    echo ""
}

menu() {
    echo -e "${YELLOW}  🐳 Docker 服务:${NC}"
    echo "    1. 启动服务      4. 查看日志      7. 重建容器"
    echo "    2. 停止服务      5. 进入容器"
    echo "    3. 重启服务      6. 健康检查"
    echo ""
    echo -e "${YELLOW}  📦 知识库同步:${NC}"
    echo "    a. 增量同步文章    c. 预览变更"
    echo "    b. 全量重置文章    d. 手动导入 (旧脚本)"
    echo ""
    echo -e "${YELLOW}  🎨 前端:${NC}"
    echo "    f. 同步 Widget 到 Hexo 主题"
    echo ""
    echo -e "${YELLOW}  🧹 其他:${NC}"
    echo "    x. 手动执行清理    q. 退出"
    echo ""
}

# ── Docker 操作 ──
cmd_start()    { $REMOTE_PREFIX "cd $SERVER_PROJECT && docker compose -f docker-compose.prod.yml up -d"; }
cmd_stop()     { $REMOTE_PREFIX "cd $SERVER_PROJECT && docker compose -f docker-compose.prod.yml down"; }
cmd_restart()  { $REMOTE_PREFIX "cd $SERVER_PROJECT && docker compose -f docker-compose.prod.yml restart agent-service"; }
cmd_logs()     { $REMOTE_PREFIX "cd $SERVER_PROJECT && docker compose -f docker-compose.prod.yml logs -f agent-service"; }
cmd_shell()    { $REMOTE_PREFIX -t "cd $SERVER_PROJECT && docker exec -it hexo-agent-service bash"; }
cmd_health()   { $REMOTE_PREFIX "curl -s http://localhost:8001/health" | python3 -m json.tool; }
cmd_rebuild()  { $REMOTE_PREFIX "cd $SERVER_PROJECT && docker compose -f docker-compose.prod.yml up -d --build agent-service"; }

# ── 知识库同步 ──
cmd_sync() {
    if [ "$MODE" == "远程" ]; then
        $REMOTE_PREFIX -t "cd $SERVER_PROJECT && python3 scripts/sync_articles.py"
    else
        echo "" && python3 scripts/sync_articles.py
    fi
}
cmd_reset() {
    if [ "$MODE" == "远程" ]; then
        $REMOTE_PREFIX -t "cd $SERVER_PROJECT && python3 scripts/sync_articles.py --reset"
    else
        echo "" && python3 scripts/sync_articles.py --reset
    fi
}
cmd_dry() {
    if [ "$MODE" == "远程" ]; then
        $REMOTE_PREFIX -t "cd $SERVER_PROJECT && python3 scripts/sync_articles.py --dry-run"
    else
        echo "" && python3 scripts/sync_articles.py --dry-run
    fi
}
cmd_import() {
    if [ "$MODE" == "远程" ]; then
        $REMOTE_PREFIX -t "cd $SERVER_PROJECT && python3 scripts/import_articles.py"
    else
        dir="${BLOG_ARTICLES_DIR:-/mnt/c/Users/22923/Desktop/blog/source/_posts}"
        echo -e "${YELLOW}文章目录: $dir${NC}"
        echo "" && python3 scripts/import_articles.py "$dir"
    fi
}

# ── 前端（始终本地执行） ──
cmd_widget() {
    bash scripts/sync-widget.sh
}

# ── 其他 ──
cmd_cleanup() {
    $REMOTE_PREFIX "cd $SERVER_PROJECT && docker exec hexo-agent-service python3 -c \"
import asyncio
from app.core.cleanup import run_cleanup
asyncio.run(run_cleanup())
\"" && echo -e "${GREEN}✅ 清理完成${NC}"
}

# ── 主循环 ──
main() {
    while true; do
        banner
        menu
        read -p "  选择操作: " choice
        echo ""

        case "$choice" in
            1) cmd_start;;
            2) cmd_stop;;
            3) cmd_restart;;
            4) cmd_logs;;
            5) cmd_shell;;
            6) cmd_health;;
            7) cmd_rebuild;;
            a) cmd_sync;;
            b) cmd_reset;;
            c) cmd_dry;;
            d) cmd_import;;
            f) cmd_widget;;
            x) cmd_cleanup;;
            q|Q) echo -e "${GREEN}👋 再见${NC}"; exit 0;;
            *) echo -e "${RED}❌ 无效选择${NC}";;
        esac

        if [ "$choice" != "4" ] && [ "$choice" != "5" ]; then
            echo ""
            read -p "  按 Enter 返回菜单..."
        fi
    done
}

main
