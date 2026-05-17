"""
知识库 API 路由模块（优化版）

提供知识库管理相关接口，支持：
- 文章创建（带 front-matter 解析）
- 文章删除
- 文章列表
- 知识库搜索
- 知识库问答
"""
import re
import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, text as sa_text
from sqlalchemy.orm import joinedload
from pydantic import BaseModel
from loguru import logger
import json

from app.core.database import get_db
from app.models.knowledge import Article, Chunk, SyncLog
from app.knowledge.chunker import chunk_markdown
from app.knowledge.embedder import embedding_service
from app.knowledge.retriever import retriever
from app.knowledge.frontmatter_parser import parse_frontmatter, normalize_categories, normalize_tags
from app.agents.knowledge_agent import knowledge_agent

router = APIRouter(prefix="/api/knowledge", tags=["知识库"])


class ArticleCreate(BaseModel):
    """创建文章请求模型"""
    title: str
    url: Optional[str] = None
    content: str
    source: str = "manual"
    date: Optional[str] = None
    categories: Optional[List[str]] = []
    tags: Optional[List[str]] = []


class SearchRequest(BaseModel):
    """搜索请求模型"""
    query: str
    top_k: int = 5


@router.post("/articles")
async def create_article(article: ArticleCreate, db: AsyncSession = Depends(get_db)):
    """
    创建文章并生成向量（支持 front-matter 解析）
    
    Args:
        article: 文章数据
    
    Returns:
        dict: 创建结果
    """
    try:
        # 检查 URL 是否已存在
        if article.url:
            existing = await db.execute(
                select(Article).where(Article.url == article.url)
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="文章 URL 已存在")
        
        # 解析 front-matter
        frontmatter = parse_frontmatter(article.content)
        
        # 提取分类和标签
        categories = normalize_categories(frontmatter.get("categories"))
        tags = normalize_tags(frontmatter.get("tags"))
        
        # 创建文章
        db_article = Article(
            title=article.title,
            url=article.url,
            content=article.content,
            source=article.source,
            synced_at=datetime.utcnow()
        )
        db.add(db_article)
        await db.flush()
        
        # 剥离 front-matter 后再分块（避免 YAML 元数据被嵌入向量）
        body = re.sub(r'^---\s*\n.*?\n---\s*\n', '', article.content, flags=re.DOTALL)
        chunks = chunk_markdown(body, file_path=article.url or article.title)
        
        # 批量生成向量
        texts = [c["content"] for c in chunks]
        embeddings = await embedding_service.embed_batch(texts)
        
        # 保存分块和向量（带元数据）
        for chunk_data, embedding in zip(chunks, embeddings):
            # 更新 metadata，添加分类、标签和日期
            metadata = chunk_data["metadata"]
            metadata["categories"] = categories
            metadata["tags"] = tags
            metadata["title"] = article.title
            if article.date:
                metadata["date"] = article.date
            
            db_chunk = Chunk(
                article_id=db_article.id,
                chunk_index=chunk_data["metadata"]["chunk_index"],
                content=chunk_data["content"],
                embedding=embedding,
                metadata_=metadata
            )
            db.add(db_chunk)
        
        await db.commit()
        
        logger.info(f"文章创建成功: {article.title}, 分类: {categories}, 分块: {len(chunks)}")
        
        return {
            "id": str(db_article.id),
            "title": article.title,
            "chunks_count": len(chunks),
            "categories": categories,
            "tags": tags
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"文章创建失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/articles/{article_id}")
async def delete_article(article_id: str, db: AsyncSession = Depends(get_db)):
    """
    删除文章及其分块
    """
    result = await db.execute(
        select(Article).where(Article.id == article_id)
    )
    article = result.scalar_one_or_none()
    
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    await db.delete(article)
    await db.commit()
    
    return {"message": "文章删除成功"}


@router.get("/articles")
async def list_articles(
    skip: int = 0,
    limit: int = 20,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    获取文章列表，支持按分类/标签筛选

    筛选走 knowledge_chunks.metadata JSONB GIN 索引，不走向量检索。
    
    Args:
        skip: 分页偏移
        limit: 每页数量
        category: 可选，按分类筛选（匹配任一）
        tag: 可选，按标签筛选（匹配任一）
    """
    if category or tag:
        filter_clauses = []
        params = {"skip": skip, "limit": limit}

        if category:
            escaped = category.replace("'", "''")
            filter_clauses.append(f"c.metadata->'categories' ?| ARRAY['{escaped}']")
        if tag:
            escaped = tag.replace("'", "''")
            filter_clauses.append(
                f"EXISTS (SELECT 1 FROM jsonb_array_elements_text(c.metadata->'tags') elem "
                f"WHERE LOWER(elem) = LOWER('{escaped}'))"
            )

        sql = sa_text(f"""
            SELECT DISTINCT ON (a.id)
                a.id, a.title, a.url, a.source, a.created_at,
                c.metadata->'categories' as categories,
                c.metadata->'tags' as tags
            FROM knowledge_articles a
            JOIN knowledge_chunks c ON c.article_id = a.id
            WHERE {' AND '.join(filter_clauses)}
            ORDER BY a.id, a.created_at DESC
            OFFSET :skip LIMIT :limit
        """)
        result = await db.execute(sql, params)
        rows = result.fetchall()

        return [{
            "id": str(row.id),
            "title": row.title,
            "url": row.url,
            "source": row.source,
            "categories": list(row.categories) if row.categories else [],
            "tags": list(row.tags) if row.tags else [],
            "created_at": row.created_at.isoformat() if row.created_at else None
        } for row in rows]

    # 无筛选参数 → 走原逻辑
    result = await db.execute(
        select(Article)
        .order_by(Article.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    articles = result.scalars().all()

    return [
        {
            "id": str(article.id),
            "title": article.title,
            "url": article.url,
            "source": article.source,
            "created_at": article.created_at.isoformat() if article.created_at else None
        }
        for article in articles
    ]


@router.post("/search")
async def search_knowledge(request: SearchRequest, db: AsyncSession = Depends(get_db)):
    """
    搜索知识库
    """
    results = await retriever.search(db, request.query, request.top_k)
    
    return [result.to_dict() for result in results]


@router.post("/chat")
async def knowledge_chat(request: SearchRequest):
    """
    知识库问答（流式输出）
    """
    async def generate():
        async for chunk in knowledge_agent.search_and_answer(request.query):
            yield f"data: {json.dumps({'content': chunk})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )
