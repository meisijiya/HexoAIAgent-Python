"""
FastAPI 应用入口模块

负责：
- 创建 FastAPI 应用实例
- 配置中间件（CORS 等）
- 管理应用生命周期
- 注册路由
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger
import os

from app.config import settings
from app.core.database import init_db, close_db
from app.core.redis import init_redis, close_redis

# 导入路由
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.knowledge import router as knowledge_router
from app.api.search import router as search_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    
    启动时：初始化数据库连接、Redis 连接
    关闭时：清理资源
    """
    # ========== 启动 ==========
    logger.info("🚀 启动 Hexo Agent Service...")
    logger.info(f"📦 版本: {settings.APP_VERSION}")
    logger.info(f"🔧 调试模式: {settings.DEBUG}")
    
    # 初始化数据库（创建表）
    await init_db()
    
    # 初始化 Redis
    await init_redis()
    
    yield
    
    # ========== 关闭 ==========
    logger.info("👋 关闭 Hexo Agent Service...")
    await close_db()
    await close_redis()


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Hexo 博客 AI Agent 服务",
    lifespan=lifespan
)

# 配置 CORS（允许跨域请求）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(knowledge_router)
app.include_router(search_router)

# 挂载静态文件
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    """
    根路径 - 返回测试页面
    """
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }


@app.get("/health")
async def health():
    """
    健康检查接口
    
    Returns:
        dict: 健康状态
    """
    return {"status": "healthy"}
