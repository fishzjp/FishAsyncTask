"""
工作线程模块

负责工作线程的创建、管理和任务执行。
支持自适应线程管理，根据CPU使用率和队列积压动态调整线程数量。

此文件保留用于向后兼容，实际实现已拆分到 worker/ 子模块。
"""

# 从子模块导入所有公共类，保持向后兼容
from .worker.adaptive import AdaptiveWorkerManager, CPUMonitor
from .worker.core import WorkerManager
from .worker.executor import TaskExecutor

__all__ = [
    "AdaptiveWorkerManager",
    "CPUMonitor",
    "TaskExecutor",
    "WorkerManager",
]
