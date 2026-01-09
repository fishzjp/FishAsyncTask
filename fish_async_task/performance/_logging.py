"""
性能优化模块的日志配置

本模块提供性能优化模块的日志记录器配置。
"""

import logging

# 创建性能优化模块的日志记录器
logger = logging.getLogger(__name__)


def configure_logging(level: int = logging.INFO) -> None:
    """
    配置性能优化模块的日志记录

    Args:
        level: 日志级别（默认：INFO）
    """
    global logger
    logger.setLevel(level)

    # 如果 logger 还没有处理器，添加控制台处理器
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)

        # 设置格式
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)

        logger.addHandler(handler)


def get_logger() -> logging.Logger:
    """
    获取性能优化模块的日志记录器

    Returns:
        logging.Logger: 日志记录器实例
    """
    return logger


# 默认配置（如果还没有配置）
if not logger.handlers:
    configure_logging()
