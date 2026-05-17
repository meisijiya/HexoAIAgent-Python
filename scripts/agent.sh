#!/bin/bash
# ===============================================================
# Hexo Agent 交互式运维脚手架
# 用法: bash scripts/agent.sh  或  ./scripts/agent.sh
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

# ── 辅助函数 ──
banner() {
    clear
    echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║       🤖 Hexo Agent 运维脚手架           ║${NC}"
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
cmd_start()    { docker compose up -d; }
cmd_stop()     { docker compose down; }
cmd_restart()  { docker compose restart agent-service; }
cmd_logs()     { docker compose logs -f agent-service; }
cmd_shell()    { docker exec -it hexo-agent-service bash; }
cmd_health()   { curl -s http://localhost:8001/health | python3 -m json.tool; }
cmd_rebuild()  { docker compose up -d --build agent-service; }

# ── 知识库同步 ──
cmd_sync() {
    echo "" && python3 scripts/sync_articles.py
}
cmd_reset() {
    echo "" && python3 scripts/sync_articles.py --reset
}
cmd_dry() {
    echo "" && python3 scripts/sync_articles.py --dry-run
}
cmd_import() {
    dir="${BLOG_ARTICLES_DIR:-/mnt/c/Users/22923/Desktop/blog/source/_posts}"
    echo -e "${YELLOW}文章目录: $dir${NC}"
    echo "" && python3 scripts/import_articles.py "$dir"
}

# ── 前端 ──
cmd_widget() {
    bash scripts/sync-widget.sh
}

# ── 其他 ──
cmd_cleanup() {
    docker exec hexo-agent-service python3 -c "
import asyncio
from app.core.cleanup import run_cleanup
asyncio.run(run_cleanup())
" && echo -e "${GREEN}✅ 清理完成${NC}"
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
