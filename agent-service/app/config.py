"""
应用配置管理模块

使用 pydantic-settings 从环境变量加载配置
支持 .env 文件和系统环境变量
"""
from pydantic_settings import BaseSettings
from pydantic import validator
from typing import Optional


class Settings(BaseSettings):
    """
    应用配置类
    
    所有配置项都可以通过环境变量覆盖，优先级：
    1. 系统环境变量
    2. .env 文件
    3. 默认值
    """
    
    # ==================== 应用基础配置 ====================
    APP_NAME: str = "Hexo Agent Service"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    
    # ==================== 数据库配置 ====================
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/hexo_agent"
    
    # ==================== Redis 配置 ====================
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # ==================== JWT 配置 ====================
    SECRET_KEY: str = "your-secret-key-change-in-production"
    
    @validator("SECRET_KEY")
    def validate_secret_key(cls, v):
        """验证 SECRET_KEY 是否为不安全默认值"""
        if v == "your-secret-key-change-in-production":
            raise ValueError(
                "请设置环境变量 SECRET_KEY（当前使用不安全默认值）"
            )
        return v
    
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 天
    
    # ==================== GitHub OAuth 配置 ====================
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    GITHUB_REDIRECT_URI: str = "http://localhost:8001/static/oauth-callback.html"
    
    # ==================== LLM 配置 ====================
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_API_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    
    # ==================== Embedding 配置 ====================
    DASHSCOPE_API_KEY: Optional[str] = None
    EMBEDDING_MODEL: str = "text-embedding-v4"
    EMBEDDING_DIMENSION: int = 1024
    
    # ==================== CORS 配置 ====================
    ALLOWED_ORIGINS: str = "http://localhost:3000,https://your-blog.github.io"
    
    # ==================== Agent 配置 ====================
    HISTORY_LIMIT: int = 3  # 对话历史轮数（默认 3 轮）
    REACT_MAX_ITERATIONS: int = 8  # ReAct Agent 最大迭代次数
    
    # ==================== 搜索引擎配置 ====================
    SEARCH_ENGINE: str = "baidu"  # 搜索引擎：baidu 或 duckduckgo
    BAIDU_SEARCH_API_KEY: Optional[str] = None  # 百度千帆搜索 API Key
    
    class Config:
        """Pydantic 配置"""
        env_file = ".env"
        env_file_encoding = "utf-8"


# 全局配置实例（单例模式）
settings = Settings()
