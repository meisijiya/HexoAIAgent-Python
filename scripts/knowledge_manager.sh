#!/bin/bash
# 知识库管理脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

show_help() {
    echo "📚 知识库管理工具"
    echo "=================="
    echo ""
    echo "用法: ./knowledge_manager.sh [命令]"
    echo ""
    echo "命令:"
    echo "  clear      - 清空所有知识库数据"
    echo "  import     - 导入文章（需要指定目录）"
    echo "  list       - 查看当前文章列表"
    echo "  stats      - 查看统计信息"
    echo "  help       - 显示帮助信息"
    echo ""
    echo "示例:"
    echo "  ./knowledge_manager.sh clear"
    echo "  ./knowledge_manager.sh import ./my-blog/source/_posts"
    echo "  ./knowledge_manager.sh list"
}

clear_knowledge() {
    echo "🗑️  清空知识库数据"
    cd "$PROJECT_DIR"
    python3 scripts/clear_knowledge.py
}

import_articles() {
    if [ -z "$1" ]; then
        echo "❌ 请指定文章目录"
        echo "用法: ./knowledge_manager.sh import <文章目录>"
        exit 1
    fi
    
    echo "📚 导入文章: $1"
    cd "$PROJECT_DIR"
    python3 scripts/import_articles.py "$1"
}

list_articles() {
    echo "📋 知识库文章列表"
    echo "=================="
    
    TOKEN=$(curl -s -X POST http://localhost:8001/api/auth/anonymous | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])")
    
    curl -s http://localhost:8001/api/knowledge/articles \
        -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if not data:
    print('📭 知识库为空')
else:
    print(f'📊 共 {len(data)} 篇文章:')
    for a in data:
        print(f'  • {a[\"title\"]}')
"
}

show_stats() {
    echo "📊 知识库统计"
    echo "=============="
    
    # 获取文章数量
    TOKEN=$(curl -s -X POST http://localhost:8001/api/auth/anonymous | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])")
    
    curl -s http://localhost:8001/api/knowledge/articles \
        -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'📄 文章数量: {len(data)}')
"
}

# 主逻辑
case "$1" in
    clear)
        clear_knowledge
        ;;
    import)
        import_articles "$2"
        ;;
    list)
        list_articles
        ;;
    stats)
        show_stats
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        show_help
        ;;
esac
