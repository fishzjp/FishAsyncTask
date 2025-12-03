"""
异步任务管理器

一个纯Python实现的异步任务管理器，支持线程池和动态伸缩。
"""

from .task_manager import TaskManager, TaskQueueFullError

__version__ = "0.1.0"
__all__ = ["TaskManager", "TaskQueueFullError"]

