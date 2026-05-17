-- ==================== 数据库初始化脚本 ====================
-- 此脚本在 PostgreSQL 容器首次启动时自动执行

-- 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 验证扩展安装
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';

-- knowledge_chunks 元数据 GIN 索引（加速分类/标签过滤）
CREATE INDEX IF NOT EXISTS idx_chunks_metadata_gin ON knowledge_chunks USING GIN (metadata);
