# PostgreSQL + pgvector 学习笔记

> Hexo Agent 项目数据库学习笔记
> 
> 更新时间：2024年

---

## 📚 目录

1. [PostgreSQL 基础](#1-postgresql-基础)
2. [pgvector 向量扩展](#2-pgvector-向量扩展)
3. [项目表结构详解](#3-项目表结构详解)
4. [常用 SQL 操作](#4-常用-sql-操作)
5. [向量搜索实战](#5-向量搜索实战)
6. [性能优化](#6-性能优化)
7. [常见问题](#7-常见问题)

---

## 1. PostgreSQL 基础

### 1.1 什么是 PostgreSQL

PostgreSQL 是一个功能强大的开源对象-关系数据库系统，具有以下特点：

- **ACID 兼容**：支持事务的原子性、一致性、隔离性、持久性
- **扩展性强**：支持自定义数据类型、函数、操作符
- **性能优秀**：支持索引、查询优化、并发控制
- **社区活跃**：丰富的插件和工具生态

### 1.2 基本数据类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `INTEGER` | 整数 | `42` |
| `BIGINT` | 大整数 | `1234567890` |
| `VARCHAR(n)` | 变长字符串 | `'hello'` |
| `TEXT` | 长文本 | `'很长的文本...'` |
| `BOOLEAN` | 布尔值 | `true/false` |
| `TIMESTAMP` | 时间戳 | `'2024-01-01 12:00:00'` |
| `UUID` | UUID | `'550e8400-e29b-41d4-a716-446655440000'` |
| `JSONB` | JSON 二进制 | `{"key": "value"}` |
| `VECTOR(n)` | 向量（pgvector） | `'[0.1, 0.2, 0.3]'` |

### 1.3 基本 SQL 语法

```sql
-- 创建表
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    email VARCHAR(200) UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 插入数据
INSERT INTO users (name, email) 
VALUES ('张三', 'zhangsan@example.com');

-- 查询数据
SELECT * FROM users WHERE name = '张三';

-- 更新数据
UPDATE users SET email = 'new@email.com' WHERE id = 'xxx';

-- 删除数据
DELETE FROM users WHERE id = 'xxx';
```

### 1.4 索引

索引是提高查询性能的关键：

```sql
-- 创建索引
CREATE INDEX idx_users_email ON users(email);

-- 创建唯一索引
CREATE UNIQUE INDEX idx_users_email ON users(email);

-- 创建复合索引
CREATE INDEX idx_users_name_email ON users(name, email);

-- 查看索引
SELECT * FROM pg_indexes WHERE tablename = 'users';

-- 删除索引
DROP INDEX idx_users_email;
```

---

## 2. pgvector 向量扩展

### 2.1 什么是 pgvector

pgvector 是 PostgreSQL 的向量相似度搜索扩展，支持：

- **向量存储**：存储高维向量数据
- **相似度计算**：余弦距离、L2 距离、内积
- **索引加速**：IVFFlat、HNSW 索引

### 2.2 安装 pgvector

```sql
-- 启用扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 验证安装
SELECT * FROM pg_extension WHERE extname = 'vector';
```

### 2.3 向量数据类型

```sql
-- 创建包含向量的表
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    content TEXT,
    embedding VECTOR(1024)  -- 1024 维向量
);

-- 插入向量数据
INSERT INTO documents (content, embedding)
VALUES (
    '这是一段文本',
    '[0.1, 0.2, 0.3, ..., 0.9]'::vector
);
```

### 2.4 向量距离计算

pgvector 支持三种距离计算方式：

| 距离类型 | 运算符 | 说明 | 适用场景 |
|----------|--------|------|----------|
| 余弦距离 | `<=>` | `1 - cos(θ)` | 文本相似度 |
| L2 距离 | `<->` | 欧几里得距离 | 图像相似度 |
| 内积 | `<#>` | 向量内积 | 推荐系统 |

```sql
-- 余弦距离（最常用）
SELECT content, 1 - (embedding <=> '[0.1, 0.2, ...]'::vector) AS similarity
FROM documents
ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector
LIMIT 5;

-- L2 距离
SELECT content, embedding <-> '[0.1, 0.2, ...]'::vector AS distance
FROM documents
ORDER BY embedding <-> '[0.1, 0.2, ...]'::vector
LIMIT 5;

-- 内积
SELECT content, embedding <#> '[0.1, 0.2, ...]'::vector AS inner_product
FROM documents
ORDER BY embedding <#> '[0.1, 0.2, ...]'::vector
LIMIT 5;
```

### 2.5 向量索引

```sql
-- IVFFlat 索引（适合中小规模数据）
CREATE INDEX ON documents 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- HNSW 索引（适合大规模数据，更精确）
CREATE INDEX ON documents 
USING hnsw (embedding vector_cosine_ops);
```

**索引选择建议**：

| 数据规模 | 推荐索引 | 原因 |
|----------|----------|------|
| < 10万 | 无索引 | 直接扫描足够快 |
| 10万-100万 | IVFFlat | 平衡速度和精度 |
| > 100万 | HNSW | 更好的召回率 |

---

## 3. 项目表结构详解

### 3.1 用户表 (agent_users)

```sql
CREATE TABLE agent_users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    github_id       BIGINT UNIQUE,
    github_username VARCHAR(100),
    nickname        VARCHAR(50),
    email           VARCHAR(100),
    avatar_url      VARCHAR(255),
    is_anonymous    BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW(),
    last_active_at  TIMESTAMP
);
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 主键，自动生成 |
| `github_id` | BIGINT | GitHub 用户 ID（OAuth 登录） |
| `github_username` | VARCHAR | GitHub 用户名 |
| `nickname` | VARCHAR | 昵称 |
| `email` | VARCHAR | 邮箱 |
| `avatar_url` | VARCHAR | 头像 URL |
| `is_anonymous` | BOOLEAN | 是否匿名用户 |
| `created_at` | TIMESTAMP | 创建时间 |
| `last_active_at` | TIMESTAMP | 最后活跃时间 |

### 3.2 会话表 (agent_sessions)

```sql
CREATE TABLE agent_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES agent_users(id) ON DELETE CASCADE,
    title       VARCHAR(200),
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 主键 |
| `user_id` | UUID | 外键，关联用户表 |
| `title` | VARCHAR | 会话标题（自动生成） |
| `created_at` | TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | 更新时间 |

**外键约束**：
- `user_id` 引用 `agent_users.id`
- `ON DELETE CASCADE`：用户删除时，会话自动删除

### 3.3 消息表 (agent_messages)

```sql
CREATE TABLE agent_messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID REFERENCES agent_sessions(id) ON DELETE CASCADE,
    role        VARCHAR(20) NOT NULL,
    content     TEXT NOT NULL,
    agent_type  VARCHAR(20),
    metadata    JSONB,
    created_at  TIMESTAMP DEFAULT NOW()
);
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 主键 |
| `session_id` | UUID | 外键，关联会话表 |
| `role` | VARCHAR | 消息角色：`user` / `assistant` |
| `content` | TEXT | 消息内容 |
| `agent_type` | VARCHAR | Agent 类型：`chat` / `knowledge` / `search` |
| `metadata` | JSONB | 扩展数据（如检索来源） |
| `created_at` | TIMESTAMP | 创建时间 |

### 3.4 知识库文章表 (knowledge_articles)

```sql
CREATE TABLE knowledge_articles (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title       VARCHAR(200) NOT NULL,
    url         VARCHAR(500) UNIQUE,
    content     TEXT,
    source      VARCHAR(20) DEFAULT 'blog',
    synced_at   TIMESTAMP,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 主键 |
| `title` | VARCHAR | 文章标题 |
| `url` | VARCHAR | 文章 URL（唯一） |
| `content` | TEXT | 文章内容 |
| `source` | VARCHAR | 来源：`blog` / `manual` |
| `synced_at` | TIMESTAMP | 同步时间 |

### 3.5 文章分块表 (knowledge_chunks) ⭐

```sql
CREATE TABLE knowledge_chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id  UUID REFERENCES knowledge_articles(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content     TEXT NOT NULL,
    embedding   VECTOR(1024),
    metadata    JSONB,
    created_at  TIMESTAMP DEFAULT NOW()
);
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 主键 |
| `article_id` | UUID | 外键，关联文章表 |
| `chunk_index` | INTEGER | 分块索引（第几块） |
| `content` | TEXT | 分块内容 |
| `embedding` | VECTOR(1024) | **1024 维向量** ⭐ |
| `metadata` | JSONB | 扩展数据（来源、索引等） |

**这是最核心的表**，存储了文章的分块和对应的向量。

### 3.6 同步日志表 (knowledge_sync_logs)

```sql
CREATE TABLE knowledge_sync_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_type    VARCHAR(20),
    status          VARCHAR(20),
    articles_count  INTEGER DEFAULT 0,
    error_message   TEXT,
    created_at      TIMESTAMP DEFAULT NOW(),
    completed_at    TIMESTAMP
);
```

---

## 4. 常用 SQL 操作

### 4.1 用户相关

```sql
-- 查询所有用户
SELECT id, nickname, is_anonymous, created_at 
FROM agent_users 
ORDER BY created_at DESC;

-- 查询匿名用户
SELECT * FROM agent_users WHERE is_anonymous = true;

-- 查询 GitHub 登录用户
SELECT * FROM agent_users WHERE github_id IS NOT NULL;

-- 统计用户数量
SELECT 
    COUNT(*) as total_users,
    COUNT(*) FILTER (WHERE is_anonymous = true) as anonymous_users,
    COUNT(*) FILTER (WHERE github_id IS NOT NULL) as github_users
FROM agent_users;
```

### 4.2 会话相关

```sql
-- 查询某用户的所有会话
SELECT s.id, s.title, s.created_at
FROM agent_sessions s
WHERE s.user_id = '用户ID'
ORDER BY s.updated_at DESC
LIMIT 10;

-- 查询会话的消息数量
SELECT 
    s.id,
    s.title,
    COUNT(m.id) as message_count
FROM agent_sessions s
LEFT JOIN agent_messages m ON s.id = m.session_id
GROUP BY s.id, s.title
ORDER BY message_count DESC;
```

### 4.3 消息相关

```sql
-- 查询某会话的所有消息
SELECT 
    m.role,
    m.content,
    m.agent_type,
    m.created_at
FROM agent_messages m
WHERE m.session_id = '会话ID'
ORDER BY m.created_at ASC;

-- 查询使用知识库 Agent 的消息
SELECT 
    m.content,
    m.metadata->'agent' as agent_info,
    m.created_at
FROM agent_messages m
WHERE m.agent_type = 'knowledge'
ORDER BY m.created_at DESC
LIMIT 10;

-- 统计各 Agent 使用次数
SELECT 
    agent_type,
    COUNT(*) as usage_count
FROM agent_messages
WHERE agent_type IS NOT NULL
GROUP BY agent_type
ORDER BY usage_count DESC;
```

### 4.4 知识库相关

```sql
-- 查询所有文章
SELECT 
    id,
    title,
    url,
    source,
    created_at
FROM knowledge_articles
ORDER BY created_at DESC;

-- 查询文章及其分块数量
SELECT 
    a.title,
    COUNT(c.id) as chunk_count,
    COUNT(c.embedding) as vector_count
FROM knowledge_articles a
LEFT JOIN knowledge_chunks c ON a.id = c.article_id
GROUP BY a.id, a.title
ORDER BY a.created_at DESC;

-- 查询某文章的所有分块
SELECT 
    c.chunk_index,
    LEFT(c.content, 100) as content_preview,
    c.embedding IS NOT NULL as has_embedding
FROM knowledge_chunks c
WHERE c.article_id = '文章ID'
ORDER BY c.chunk_index;
```

---

## 5. 向量搜索实战

### 5.1 基本搜索流程

```sql
-- 步骤 1: 将查询文本转换为向量（在应用层完成）
-- 假设查询向量为: [0.1, 0.2, 0.3, ..., 0.9]

-- 步骤 2: 使用余弦距离搜索最相似的文档
SELECT 
    c.id,
    c.content,
    1 - (c.embedding <=> '[0.1, 0.2, ..., 0.9]'::vector) as similarity
FROM knowledge_chunks c
ORDER BY c.embedding <=> '[0.1, 0.2, ..., 0.9]'::vector
LIMIT 5;

-- 步骤 3: 返回相似度 > 0.3 的结果
SELECT 
    c.id,
    c.content,
    1 - (c.embedding <=> '[0.1, 0.2, ..., 0.9]'::vector) as similarity
FROM knowledge_chunks c
WHERE 1 - (c.embedding <=> '[0.1, 0.2, ..., 0.9]'::vector) > 0.3
ORDER BY c.embedding <=> '[0.1, 0.2, ..., 0.9]'::vector
LIMIT 5;
```

### 5.2 带元数据的搜索

```sql
-- 搜索并返回文章信息
SELECT 
    c.id,
    c.content,
    a.title as article_title,
    a.url as article_url,
    1 - (c.embedding <=> query_vec) as similarity
FROM knowledge_chunks c
JOIN knowledge_articles a ON c.article_id = a.id
WHERE 1 - (c.embedding <=> query_vec) > 0.3
ORDER BY c.embedding <=> query_vec
LIMIT 5;
```

### 5.3 按来源过滤搜索

```sql
-- 只搜索特定来源的文章
SELECT 
    c.id,
    c.content,
    1 - (c.embedding <=> query_vec) as similarity
FROM knowledge_chunks c
JOIN knowledge_articles a ON c.article_id = a.id
WHERE a.source = 'blog'
  AND 1 - (c.embedding <=> query_vec) > 0.3
ORDER BY c.embedding <=> query_vec
LIMIT 5;
```

### 5.4 批量搜索

```sql
-- 同时搜索多个查询
WITH queries AS (
    SELECT 1 as query_id, '[0.1, 0.2, ...]'::vector as query_vec
    UNION ALL
    SELECT 2 as query_id, '[0.3, 0.4, ...]'::vector as query_vec
)
SELECT 
    q.query_id,
    c.id,
    c.content,
    1 - (c.embedding <=> q.query_vec) as similarity
FROM queries q
CROSS JOIN LATERAL (
    SELECT id, content, embedding
    FROM knowledge_chunks
    ORDER BY embedding <=> q.query_vec
    LIMIT 3
) c
ORDER BY q.query_id, similarity DESC;
```

---

## 6. 性能优化

### 6.1 索引优化

```sql
-- 查看索引使用情况
SELECT 
    indexrelname as index_name,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE relname = 'knowledge_chunks';

-- 分析查询性能
EXPLAIN ANALYZE
SELECT * FROM knowledge_chunks
ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector
LIMIT 5;
```

### 6.2 查询优化

```sql
-- 使用 LIMIT 限制返回数量
-- 避免返回所有结果

-- 使用 WHERE 过滤
-- 减少需要计算的距离数量

-- 使用 EXPLAIN ANALYZE 分析
-- 查看是否使用了索引
```

### 6.3 向量索引参数调优

```sql
-- IVFFlat 索引参数
CREATE INDEX ON knowledge_chunks 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);  -- lists = sqrt(行数)

-- 查看索引大小
SELECT pg_size_pretty(pg_relation_size('knowledge_chunks_embedding_idx'));
```

### 6.4 连接池配置

```python
# SQLAlchemy 连接池配置
engine = create_async_engine(
    DATABASE_URL,
    pool_size=5,        # 连接池大小
    max_overflow=10,    # 最大溢出连接数
    pool_timeout=30,    # 连接超时时间
    pool_recycle=1800   # 连接回收时间
)
```

---

## 7. 常见问题

### 7.1 向量维度不匹配

**错误信息**：
```
ERROR: vector must have 1024 dimensions
```

**原因**：插入的向量维度与表定义不匹配

**解决方案**：
```sql
-- 检查表定义
SELECT column_name, data_type, character_maximum_length
FROM information_schema.columns
WHERE table_name = 'knowledge_chunks' AND column_name = 'embedding';

-- 确保插入的向量维度正确
INSERT INTO knowledge_chunks (embedding)
VALUES ('[0.1, 0.2, ..., 0.9]'::vector);  -- 必须是 1024 维
```

### 7.2 向量格式错误

**错误信息**：
```
ERROR: invalid input syntax for type vector
```

**原因**：向量格式不正确

**解决方案**：
```sql
-- 正确格式
SELECT '[0.1, 0.2, 0.3]'::vector;

-- 错误格式
SELECT '0.1, 0.2, 0.3'::vector;  -- 缺少方括号
SELECT '[0.1 0.2 0.3]'::vector;   -- 缺少逗号
```

### 7.3 搜索结果为空

**可能原因**：

1. **向量未生成**
   ```sql
   SELECT COUNT(*) FROM knowledge_chunks WHERE embedding IS NULL;
   ```

2. **相似度阈值太高**
   ```sql
   -- 降低阈值
   SELECT * FROM knowledge_chunks
   WHERE 1 - (embedding <=> query_vec) > 0.1;  -- 从 0.3 降到 0.1
   ```

3. **向量数据损坏**
   ```sql
   -- 检查向量数据
   SELECT id, embedding FROM knowledge_chunks LIMIT 5;
   ```

### 7.4 性能问题

**问题**：搜索很慢

**解决方案**：

1. **创建索引**
   ```sql
   CREATE INDEX ON knowledge_chunks 
   USING ivfflat (embedding vector_cosine_ops);
   ```

2. **减少返回数量**
   ```sql
   LIMIT 5  -- 而不是返回所有
   ```

3. **使用 WHERE 过滤**
   ```sql
   WHERE article_id = 'xxx'
   ```

### 7.5 数据一致性

**问题**：文章删除了，但分块还在

**解决方案**：
```sql
-- 使用外键约束（已配置）
-- ON DELETE CASCADE 会自动删除关联的分块

-- 手动清理孤立数据
DELETE FROM knowledge_chunks 
WHERE article_id NOT IN (SELECT id FROM knowledge_articles);
```

---

## 📚 参考资源

- [PostgreSQL 官方文档](https://www.postgresql.org/docs/)
- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [pgvector 使用指南](https://github.com/pgvector/pgvector#querying)
- [SQLAlchemy 异步文档](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)

---

## 🧪 练习

### 练习 1：基本查询

```sql
-- 1. 查询所有匿名用户
-- 2. 查询最近创建的 5 个会话
-- 3. 统计每个 Agent 的使用次数
```

### 练习 2：向量搜索

```sql
-- 1. 查询所有已生成向量的分块数量
-- 2. 搜索与某个文本最相似的 3 个分块
-- 3. 搜索某篇文章中最相似的分块
```

### 练习 3：数据分析

```sql
-- 1. 统计每天的对话数量
-- 2. 找出最活跃的用户
-- 3. 分析各 Agent 的使用趋势
```

---

**祝学习顺利！** 🎉
