"""
结构化日志模块

提供结构化日志记录功能，支持JSON格式输出和上下文信息。
"""

import json
import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional


class StructuredLogger:
    """结构化日志记录器"""

    def __init__(self, logger: logging.Logger):
        """
        初始化结构化日志记录器

        Args:
            logger: 标准日志记录器
        """
        self._logger = logger
        self._context: Dict[str, Any] = {}
        self._context_lock = threading.Lock()

    def set_context(self, **kwargs: Any) -> None:
        """
        设置日志上下文

        Args:
            **kwargs: 上下文键值对
        """
        with self._context_lock:
            self._context.update(kwargs)

    def clear_context(self) -> None:
        """清除日志上下文"""
        with self._context_lock:
            self._context.clear()

    def _format_message(
        self,
        message: str,
        extra_context: Dict[str, Any] = None,
        include_timestamp: bool = True,
    ) -> str:
        """
        格式化日志消息

        Args:
            message: 日志消息
            extra_context: 额外上下文
            include_timestamp: 是否包含时间戳

        Returns:
            str: 格式化后的JSON字符串
        """
        with self._context_lock:
            context = dict(self._context)

        if extra_context:
            context.update(extra_context)

        log_data = {}

        if include_timestamp:
            log_data["timestamp"] = datetime.now().isoformat()

        log_data["message"] = message

        if context:
            log_data["context"] = context

        return json.dumps(log_data)

    def debug(self, message: str, **kwargs: Any) -> None:
        """调试级别日志"""
        self._logger.debug(self._format_message(message, kwargs))

    def info(self, message: str, **kwargs: Any) -> None:
        """信息级别日志"""
        self._logger.info(self._format_message(message, kwargs))

    def warning(self, message: str, **kwargs: Any) -> None:
        """警告级别日志"""
        self._logger.warning(self._format_message(message, kwargs))

    def error(self, message: str, exc_info: bool = False, **kwargs: Any) -> None:
        """
        错误级别日志

        Args:
            message: 日志消息
            exc_info: 是否包含异常堆栈
            **kwargs: 额外上下文
        """
        self._logger.error(self._format_message(message, kwargs), exc_info=exc_info)

    def critical(
        self, message: str, exc_info: bool = False, **kwargs: Any
    ) -> None:
        """
        严重错误级别日志

        Args:
            message: 日志消息
            exc_info: 是否包含异常堆栈
            **kwargs: 额外上下文
        """
        self._logger.critical(self._format_message(message, kwargs), exc_info=exc_info)

    def log_exception(
        self,
        message: str,
        exception: Exception,
        context: Dict[str, Any] = None,
    ) -> None:
        """
        记录异常信息

        Args:
            message: 日志消息
            exception: 异常对象
            context: 额外上下文
        """
        error_context = {
            "exception_type": type(exception).__name__,
            "exception_message": str(exception),
        }

        if context:
            error_context.update(context)

        self._logger.error(
            self._format_message(message, error_context), exc_info=True
        )


class ContextLogger:
    """上下文日志记录器 - 支持自动上下文管理"""

    def __init__(self, logger: logging.Logger):
        """
        初始化上下文日志记录器

        Args:
            logger: 标准日志记录器
        """
        self._logger = StructuredLogger(logger)
        self._context_stack: list = []

    def push_context(self, **kwargs: Any) -> "ContextLogger":
        """
        推入新的上下文层

        Args:
            **kwargs: 上下文键值对

        Returns:
            ContextLogger: 返回self以支持链式调用
        """
        self._logger.set_context(**kwargs)
        self._context_stack.append(kwargs)
        return self

    def pop_context(self) -> None:
        """弹出上下文层"""
        if self._context_stack:
            self._context_stack.pop()

        if self._context_stack:
            self._logger.clear_context()
            for ctx in self._context_stack:
                self._logger.set_context(**ctx)
        else:
            self._logger.clear_context()

    def __enter__(self) -> "ContextLogger":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.pop_context()

    def debug(self, message: str, **kwargs: Any) -> None:
        self._logger.debug(message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._logger.warning(message, **kwargs)

    def error(self, message: str, exc_info: bool = False, **kwargs: Any) -> None:
        self._logger.error(message, exc_info=exc_info, **kwargs)

    def critical(
        self, message: str, exc_info: bool = False, **kwargs: Any
    ) -> None:
        self._logger.critical(message, exc_info=exc_info, **kwargs)


def get_structured_logger(name: str) -> StructuredLogger:
    """
    获取结构化日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        StructuredLogger: 结构化日志记录器
    """
    return StructuredLogger(logging.getLogger(name))


def get_context_logger(name: str) -> ContextLogger:
    """
    获取上下文日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        ContextLogger: 上下文日志记录器
    """
    return ContextLogger(logging.getLogger(name))
