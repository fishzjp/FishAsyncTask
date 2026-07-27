"""
Python/Rust 统一适配器

提供统一的接口，自动选择 Rust 或 Python 实现。
队列空/满统一抛标准库 queue.Empty / queue.Full。
"""

import queue as _stdlib_queue
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from .types import TaskStatusDict

if TYPE_CHECKING:
    from ._rust import (
        PyPriorityTaskQueue,
        PyShardedTaskStatus,
        PyTaskDependencyManager,
    )

# 尝试导入 Rust 实现
try:
    from ._rust import (
        PyPriorityTaskQueue,
        PyShardedTaskStatus,
        PyTaskDependencyManager,
    )

    _RUST_AVAILABLE = True
except ImportError:
    _RUST_AVAILABLE = False
    PyShardedTaskStatus = None
    PyPriorityTaskQueue = None
    PyTaskDependencyManager = None


from .performance.priority_queue import PriorityTaskQueue as PythonPriorityTaskQueue

# 导入 Python 回退实现
from .task_status import ShardedTaskStatusWithExpiry


class ShardedTaskStatusAdapter:
    """
    分片状态存储适配器

    自动选择 Rust 或 Python 实现。
    """

    @classmethod
    def create(cls, shard_count: int = 16, ttl: int = 3600) -> "ShardedTaskStatusAdapter":
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

    def update_status(self, task_id: str, status: TaskStatusDict, current_status: Optional[TaskStatusDict] = None) -> None:
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

    def enforce_max_count(self, max_count: int) -> int:
        """强制执行最大任务数量限制"""
        raise NotImplementedError

    def resize_shards(self, new_shard_count: int) -> bool:
        """动态调整分片数量"""
        raise NotImplementedError

    @property
    def shard_count(self) -> int:
        """获取当前分片数量"""
        raise NotImplementedError


class _RustShardedTaskStatusAdapter(ShardedTaskStatusAdapter):
    """Rust 实现适配器"""

    def __init__(self, shard_count: int, ttl: int) -> None:
        self._rust: "PyShardedTaskStatus" = PyShardedTaskStatus(shard_count, ttl)  # type: ignore[name-defined]

    def get_status(self, task_id: str) -> Optional[TaskStatusDict]:
        # Rust 直接返回正确格式的字典，无需二次转换
        return self._rust.get_status(task_id)

    def update_status(self, task_id: str, status: TaskStatusDict, current_status: Optional[TaskStatusDict] = None) -> None:
        # 当需要 result 或 error 字段时，使用完整 update_status 方法
        # 其他情况使用高性能 update_status_fast 方法
        # current_status 参数被忽略（Rust 实现内部处理状态合并）
        if "result" in status or "error" in status:
            # 使用字典方式更新以支持 result 和 error
            self._rust.update_status(task_id, status)
        else:
            # 使用高性能 API，直接传递参数避免字典转换开销
            self._rust.update_status_fast(
                task_id,
                status.get("status") or "pending",
                status.get("submit_time"),
                status.get("start_time"),
                status.get("end_time"),
                status.get("worker_id"),
            )

    def remove_status(self, task_id: str) -> bool:
        return self._rust.remove_status(task_id)

    def cleanup_expired(self, max_cleanup: Optional[int] = None) -> int:
        """清理过期任务"""
        return self._rust.cleanup_expired(max_cleanup)

    def get_total_count(self) -> int:
        return self._rust.get_total_count()

    def clear_all(self) -> None:
        self._rust.clear_all()

    def enforce_max_count(self, max_count: int) -> int:
        """强制执行最大任务数量限制"""
        return self._rust.enforce_max_count(max_count)

    def resize_shards(self, new_shard_count: int) -> bool:
        """动态调整分片数量"""
        # Rust 实现不支持动态调整分片数量（需要重新创建实例）
        # 调用 Rust 方法会返回 false
        return self._rust.resize_shards(new_shard_count)

    @property
    def shard_count(self) -> int:
        """获取当前分片数量"""
        return self._rust.get_shard_count()


class _PythonShardedTaskStatusAdapter(ShardedTaskStatusAdapter):
    """Python 实现适配器（回退）"""

    def __init__(self, shard_count: int, ttl: int) -> None:
        self._inner: ShardedTaskStatusWithExpiry = ShardedTaskStatusWithExpiry(shard_count, ttl)

    def get_status(self, task_id: str) -> Optional[TaskStatusDict]:
        return self._inner.get_status(task_id)

    def update_status(self, task_id: str, status: TaskStatusDict, current_status: Optional[TaskStatusDict] = None) -> None:
        self._inner.update_status(task_id, status, current_status)

    def remove_status(self, task_id: str) -> bool:
        return self._inner.remove_status(task_id)

    def cleanup_expired(self, max_cleanup: Optional[int] = None) -> int:
        return self._inner.cleanup_expired(max_cleanup)

    def get_total_count(self) -> int:
        return self._inner.get_total_count()

    def clear_all(self) -> None:
        self._inner.clear_all()

    def enforce_max_count(self, max_count: int) -> int:
        """强制执行最大任务数量限制"""
        return self._inner.enforce_max_count(max_count)

    def resize_shards(self, new_shard_count: int) -> bool:
        """动态调整分片数量"""
        return self._inner.resize_shards(new_shard_count)

    @property
    def shard_count(self) -> int:
        """获取当前分片数量"""
        return self._inner.shard_count


class PriorityTaskQueueAdapter:
    """
    优先级队列适配器

    自动选择 Rust 或 Python 实现。
    """

    @classmethod
    def create(cls, maxsize: int = 1000) -> "PriorityTaskQueueAdapter":
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

    def put(
        self, task_id: str, priority: int, block: bool = True, timeout: Optional[float] = None
    ) -> None:
        """向队列添加任务；队列满（非阻塞或等待超时）抛 queue.Full"""
        raise NotImplementedError

    def get(self, block: bool = True, timeout: Optional[float] = None) -> str:
        """从队列获取任务ID；队列空（非阻塞或等待超时）抛 queue.Empty"""
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

    def clear(self) -> None:
        """清空队列"""
        raise NotImplementedError


class _RustPriorityTaskQueueAdapter(PriorityTaskQueueAdapter):
    """Rust 优先级队列适配器"""

    def __init__(self, maxsize: int) -> None:
        self._rust: "PyPriorityTaskQueue" = PyPriorityTaskQueue(maxsize)  # type: ignore[name-defined]

    def put(
        self, task_id: str, priority: int, block: bool = True, timeout: Optional[float] = None
    ) -> None:
        import time

        # Rust 侧满/超时返回 False，映射为标准库 queue.Full
        if not self._rust.put(priority, task_id, time.time(), block, timeout):
            raise _stdlib_queue.Full()

    def get(self, block: bool = True, timeout: Optional[float] = None) -> str:
        # Rust 侧空/超时返回 None，映射为标准库 queue.Empty
        task_id = self._rust.get(block, timeout)
        if task_id is None:
            raise _stdlib_queue.Empty()
        return task_id

    def qsize(self) -> int:
        return self._rust.qsize()

    def empty(self) -> bool:
        return self._rust.empty()

    def full(self) -> bool:
        return self._rust.full()

    def clear(self) -> None:
        self._rust.clear()


class _PythonPriorityTaskQueueAdapter(PriorityTaskQueueAdapter):
    """Python 优先级队列适配器（回退）"""

    def __init__(self, maxsize: int) -> None:
        self._inner: PythonPriorityTaskQueue = PythonPriorityTaskQueue(maxsize=maxsize)

    def put(
        self, task_id: str, priority: int, block: bool = True, timeout: Optional[float] = None
    ) -> None:
        # Python PriorityTaskQueue 需要完整的任务对象
        import time

        from .performance.priority_queue import PrioritizedTask

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

    def clear(self) -> None:
        self._inner.clear()


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
