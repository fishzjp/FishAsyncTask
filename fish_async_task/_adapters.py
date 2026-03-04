"""
Python/Rust 统一适配器

提供统一的接口，自动选择 Rust 或 Python 实现。
"""

from typing import Optional, Union, List, Any
from .types import TaskStatusDict

# 尝试导入 Rust 实现
try:
    from ._rust import (
        PyShardedTaskStatus,
        PyPriorityTaskQueue,
        PyTaskDependencyManager,
    )
    _RUST_AVAILABLE = True
except ImportError:
    _RUST_AVAILABLE = False
    PyShardedTaskStatus = None
    PyPriorityTaskQueue = None
    PyTaskDependencyManager = None


# 导入 Python 回退实现
from .task_status import ShardedTaskStatusWithExpiry
from .performance.priority_queue import PriorityTaskQueue as PythonPriorityTaskQueue


class ShardedTaskStatusAdapter:
    """
    分片状态存储适配器

    自动选择 Rust 或 Python 实现。
    """

    @classmethod
    def create(cls, shard_count: int = 16, ttl: int = 3600):
        """
        创建状态存储实例

        Args:
            shard_count: 分片数量
            ttl: 任务状态生存时间（秒）

        Returns:
            状态存储实例（Rust 或 Python 实现）
        """
        if _RUST_AVAILABLE:
            return _RustShardedTaskStatusAdapter(shard_count, ttl)
        else:
            return _PythonShardedTaskStatusAdapter(shard_count, ttl)

    def get_status(self, task_id: str) -> Optional[TaskStatusDict]:
        """获取任务状态"""
        raise NotImplementedError

    def update_status(self, task_id: str, status: TaskStatusDict) -> None:
        """更新任务状态"""
        raise NotImplementedError

    def remove_status(self, task_id: str) -> bool:
        """移除任务状态"""
        raise NotImplementedError

    def cleanup_expired(self, max_cleanup: Optional[int] = None) -> int:
        """清理过期任务"""
        raise NotImplementedError

    def get_total_count(self) -> int:
        """获取总任务数量"""
        raise NotImplementedError

    def clear_all(self) -> None:
        """清空所有任务状态"""
        raise NotImplementedError


class _RustShardedTaskStatusAdapter(ShardedTaskStatusAdapter):
    """Rust 实现适配器"""

    def __init__(self, shard_count: int, ttl: int):
        self._rust = PyShardedTaskStatus(shard_count, ttl)

    def get_status(self, task_id: str) -> Optional[TaskStatusDict]:
        result = self._rust.get_status(task_id)
        if result is None:
            return None
        # 转换为 TaskStatusDict
        return {
            "status": result.get("status"),
            "submit_time": result.get("submit_time"),
            "start_time": result.get("start_time"),
            "end_time": result.get("end_time"),
            "result": result.get("result"),
            "error": result.get("error"),
            "worker_id": result.get("worker_id"),
        }

    def update_status(self, task_id: str, status: TaskStatusDict) -> None:
        # 转换为 Rust 需要的格式
        self._rust.update_status(task_id, status)

    def remove_status(self, task_id: str) -> bool:
        return self._rust.remove_status(task_id)

    def cleanup_expired(self, max_cleanup: Optional[int] = None) -> int:
        return self._rust.cleanup_expired(max_cleanup)

    def get_total_count(self) -> int:
        return self._rust.get_total_count()

    def clear_all(self) -> None:
        self._rust.clear_all()


class _PythonShardedTaskStatusAdapter(ShardedTaskStatusAdapter):
    """Python 实现适配器（回退）"""

    def __init__(self, shard_count: int, ttl: int):
        self._inner = ShardedTaskStatusWithExpiry(shard_count, ttl)

    def get_status(self, task_id: str) -> Optional[TaskStatusDict]:
        return self._inner.get_status(task_id)

    def update_status(self, task_id: str, status: TaskStatusDict) -> None:
        self._inner.update_status(task_id, status)

    def remove_status(self, task_id: str) -> bool:
        return self._inner.remove_status(task_id)

    def cleanup_expired(self, max_cleanup: Optional[int] = None) -> int:
        return self._inner.cleanup_expired(max_cleanup)

    def get_total_count(self) -> int:
        return self._inner.get_total_count()

    def clear_all(self) -> None:
        self._inner.clear_all()


class PriorityTaskQueueAdapter:
    """
    优先级队列适配器

    自动选择 Rust 或 Python 实现。
    """

    @classmethod
    def create(cls, maxsize: int = 1000):
        """
        创建优先级队列实例

        Args:
            maxsize: 最大队列大小

        Returns:
            优先级队列实例（Rust 或 Python 实现）
        """
        if _RUST_AVAILABLE:
            return _RustPriorityTaskQueueAdapter(maxsize)
        else:
            return _PythonPriorityTaskQueueAdapter(maxsize)

    def put(self, task_id: str, priority: int, block: bool = True, timeout: Optional[float] = None) -> None:
        """向队列添加任务"""
        raise NotImplementedError

    def get(self, block: bool = True, timeout: Optional[float] = None) -> str:
        """从队列获取任务ID"""
        raise NotImplementedError

    def qsize(self) -> int:
        """获取队列大小"""
        raise NotImplementedError

    def empty(self) -> bool:
        """检查队列是否为空"""
        raise NotImplementedError

    def full(self) -> bool:
        """检查队列是否已满"""
        raise NotImplementedError


class _RustPriorityTaskQueueAdapter(PriorityTaskQueueAdapter):
    """Rust 优先级队列适配器"""

    def __init__(self, maxsize: int):
        import time
        self._rust = PyPriorityTaskQueue(maxsize)
        self._tasks = {}  # task_id -> (priority, task_id, submit_time)

    def put(self, task_id: str, priority: int, block: bool = True, timeout: Optional[float] = None) -> None:
        import time
        submit_time = time.time()
        self._tasks[task_id] = (priority, task_id, submit_time)
        self._rust.put(priority, task_id, submit_time, block, timeout)

    def get(self, block: bool = True, timeout: Optional[float] = None) -> str:
        return self._rust.get(block, timeout)

    def qsize(self) -> int:
        return self._rust.qsize()

    def empty(self) -> bool:
        return self._rust.empty()

    def full(self) -> bool:
        return self._rust.full()


class _PythonPriorityTaskQueueAdapter(PriorityTaskQueueAdapter):
    """Python 优先级队列适配器（回退）"""

    def __init__(self, maxsize: int):
        self._inner = PythonPriorityTaskQueue(maxsize=maxsize)

    def put(self, task_id: str, priority: int, block: bool = True, timeout: Optional[float] = None) -> None:
        # Python PriorityTaskQueue 需要完整的任务对象
        from .performance.priority_queue import PrioritizedTask
        import time
        task = PrioritizedTask(
            priority=priority,
            task_id=task_id,
            func=lambda: None,
            args=(),
            kwargs={},
            submit_time=time.time(),
        )
        self._inner.put(task, block=block, timeout=timeout)

    def get(self, block: bool = True, timeout: Optional[float] = None) -> str:
        task = self._inner.get(block=block, timeout=timeout)
        return task.task_id

    def qsize(self) -> int:
        return self._inner.qsize()

    def empty(self) -> bool:
        return self._inner.empty()

    def full(self) -> bool:
        return self._inner.full()


def get_sharded_status_store(shard_count: int = 16, ttl: int = 3600) -> ShardedTaskStatusAdapter:
    """
    获取分片状态存储实例（优先使用 Rust 实现）

    Args:
        shard_count: 分片数量
        ttl: 任务状态生存时间（秒）

    Returns:
        状态存储实例
    """
    return ShardedTaskStatusAdapter.create(shard_count, ttl)


def get_priority_queue(maxsize: int = 1000) -> PriorityTaskQueueAdapter:
    """
    获取优先级队列实例（优先使用 Rust 实现）

    Args:
        maxsize: 最大队列大小

    Returns:
        优先级队列实例
    """
    return PriorityTaskQueueAdapter.create(maxsize)


def is_rust_available() -> bool:
    """检查 Rust 扩展是否可用"""
    return _RUST_AVAILABLE
