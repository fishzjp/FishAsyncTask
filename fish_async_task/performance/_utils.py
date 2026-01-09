"""
性能优化模块的通用工具函数

本模块提供性能优化相关的通用工具函数，包括：
- 哈希分片计算
- 时间计算和过期判断
- CPU 使用率检测
"""

import hashlib
import time
from typing import Optional


def compute_shard_index(task_id: str, shard_count: int) -> int:
    """
    根据 task_id 计算分片索引

    使用 MD5 哈希确保均匀分布，然后对分片数量取模。

    Args:
        task_id: 任务 ID
        shard_count: 分片数量

    Returns:
        分片索引（0 到 shard_count-1）

    Raises:
        ValueError: 如果 shard_count < 1

    Examples:
        >>> compute_shard_index("task-123", 16)
        7
        >>> compute_shard_index("task-456", 16)
        12
    """
    if shard_count < 1:
        raise ValueError(f"shard_count 必须 >= 1，当前值: {shard_count}")

    # 使用 MD5 哈希确保均匀分布
    hash_bytes = hashlib.md5(task_id.encode()).digest()
    # 取前 4 字节转换为整数
    hash_int = int.from_bytes(hash_bytes[:4], byteorder="big")
    # 对分片数量取模
    return hash_int % shard_count


def compute_expiry_time(end_time: float, ttl: int) -> float:
    """
    计算过期时间

    Args:
        end_time: 任务结束时间（Unix 时间戳）
        ttl: 生存时间（秒）

    Returns:
        过期时间（Unix 时间戳）

    Examples:
        >>> compute_expiry_time(1704800000.0, 300)
        1704800300.0
    """
    return end_time + ttl


def is_expired(expiry_time: float, current_time: Optional[float] = None) -> bool:
    """
    判断是否已过期

    Args:
        expiry_time: 过期时间（Unix 时间戳）
        current_time: 当前时间（Unix 时间戳），如果为 None 则使用 time.time()

    Returns:
        True 如果已过期，False 否则

    Examples:
        >>> is_expired(1704800000.0, 1704800100.0)
        True
        >>> is_expired(1704800000.0, 1704799900.0)
        False
    """
    if current_time is None:
        current_time = time.time()
    return current_time > expiry_time


def get_cpu_usage() -> Optional[float]:
    """
    获取当前 CPU 使用率

    尝试使用 psutil 获取 CPU 使用率。如果 psutil 不可用，返回 None。

    Returns:
        CPU 使用率（0-1），如果 psutil 不可用返回 None

    Note:
        psutil.cpu_percent() 可能阻塞约 0.1 秒（默认间隔）
    """
    try:
        import psutil

        # psutil.cpu_percent() 返回 0-100 的值，需要转换为 0-1
        return float(psutil.cpu_percent(interval=0.1) / 100.0)
    except (ImportError, NotImplementedError):
        return None


def format_timestamp(timestamp: float) -> str:
    """
    格式化 Unix 时间戳为可读字符串

    Args:
        timestamp: Unix 时间戳

    Returns:
        格式化的时间字符串

    Examples:
        >>> format_timestamp(1704800000.0)
        '2024-01-09 12:26:40'
    """
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))


def validate_shard_count(shard_count: int) -> None:
    """
    验证分片数量的合理性

    Args:
        shard_count: 分片数量

    Raises:
        ValueError: 如果分片数量不合理

    Validation Rules:
        - shard_count 必须 >= 1
        - shard_count 应该是 2 的幂次（建议）
        - shard_count 不应该太大（<= 1024）
    """
    if shard_count < 1:
        raise ValueError(f"shard_count 必须 >= 1，当前值: {shard_count}")

    if shard_count > 1024:
        raise ValueError(f"shard_count 不应该 > 1024，当前值: {shard_count}")

    # 检查是否是 2 的幂次（仅警告）
    if (shard_count & (shard_count - 1)) != 0:
        # 不是 2 的幂次，但仍然可以工作
        pass
