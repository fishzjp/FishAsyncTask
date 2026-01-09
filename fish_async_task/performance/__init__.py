"""
FishAsyncTask 性能优化模块

本模块提供性能优化功能，包括：
- 分片任务状态存储（ShardedTaskStatus）
- 优先级队列清理（TaskStatusWithExpiry）
- 批量状态更新（BatchedStatusUpdater）
- 自适应工作线程管理（AdaptiveWorkerManager）

所有优化遵循轻量化原则，核心功能仅使用 Python 标准库。
"""

from typing import TYPE_CHECKING

from .adaptive_scaling import AdaptiveWorkerManager
from .batch_updater import BatchedStatusUpdater
from .priority_cleanup import TaskStatusWithExpiry

# 导入已实现的类
from .sharded_status import ShardedTaskStatus

__all__ = [
    "ShardedTaskStatus",
    "TaskStatusWithExpiry",
    "BatchedStatusUpdater",
    "AdaptiveWorkerManager",
]

# 版本信息
__version__ = "0.1.0"
