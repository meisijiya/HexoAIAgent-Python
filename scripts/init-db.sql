-- ==================== 数据库初始化脚本 ====================
-- 此脚本在 PostgreSQL 容器首次启动时自动执行
-- 注意：表结构由 FastAPI create_all 创建，这里只做扩展安装

-- 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 验证扩展安装
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
