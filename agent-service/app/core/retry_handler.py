"""
错误重试模块

负责：
- API 调用失败重试
- 指数退避策略
- 错误日志记录
"""
import asyncio
from typing import Callable, Any, Optional
from functools import wraps
from loguru import logger


class RetryHandler:
    """
    错误重试处理器
    
    支持：
    - 最大重试次数
    - 指数退避
    - 自定义异常类型
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 10.0,
        exceptions: tuple = (Exception,)
    ):
        """
        初始化重试处理器
        
        Args:
            max_retries: 最大重试次数
            base_delay: 基础延迟时间（秒）
            max_delay: 最大延迟时间（秒）
            exceptions: 需要重试的异常类型
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exceptions = exceptions
    
    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """
        执行函数（带重试）
        
        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数
        
        Returns:
            Any: 函数返回值
        
        Raises:
            Exception: 最后一次重试仍然失败的异常
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except self.exceptions as e:
                last_exception = e
                
                if attempt < self.max_retries:
                    # 计算延迟时间（指数退避）
                    delay = min(
                        self.base_delay * (2 ** attempt),
                        self.max_delay
                    )
                    
                    logger.warning(
                        f"调用失败，{delay:.1f}秒后重试 "
                        f"(尝试 {attempt + 1}/{self.max_retries + 1}): {e}"
                    )
                    
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"调用失败，已达到最大重试次数 "
                        f"(尝试 {attempt + 1}/{self.max_retries + 1}): {e}"
                    )
        
        raise last_exception


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exceptions: tuple = (Exception,)
):
    """
    重试装饰器
    
    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟时间（秒）
        max_delay: 最大延迟时间（秒）
        exceptions: 需要重试的异常类型
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            handler = RetryHandler(
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                exceptions=exceptions
            )
            return await handler.execute(func, *args, **kwargs)
        return wrapper
    return decorator


# 创建默认重试处理器
default_retry_handler = RetryHandler()


# 创建 HTTP 请求重试处理器
http_retry_handler = RetryHandler(
    max_retries=3,
    base_delay=1.0,
    max_delay=5.0,
    exceptions=(
        Exception,  # 可以指定更具体的异常类型
    )
)
