"""Cython 性能优化模块

本模块提供 Cython 编译的性能优化实现。
如果 Cython 扩展未编译，将自动回退到纯 Python 实现。
"""

import sys
from pathlib import Path

# 尝试导入 Cython 编译的扩展
CYTHON_AVAILABLE = False

try:
    # 尝试导入 Cython 编译的分片存储
    from . import _priority_queue  # noqa: F401
    from . import _sharded_status  # noqa: F401

    # 如果导入成功，导出 Cython 实现的类
    ShardedTaskStatus = _sharded_status.ShardedTaskStatus  # noqa: F401
    TaskStatusWithExpiry = _priority_queue.TaskStatusWithExpiry  # noqa: F401

    CYTHON_AVAILABLE = True

except (ImportError, ModuleNotFoundError):
    # Cython 扩展不可用，使用纯 Python 实现
    from fish_async_task.performance.priority_cleanup import TaskStatusWithExpiry
    from fish_async_task.performance.sharded_status import ShardedTaskStatus

    CYTHON_AVAILABLE = False

__all__ = [
    "CYTHON_AVAILABLE",
    "ShardedTaskStatus",
    "TaskStatusWithExpiry",
]
