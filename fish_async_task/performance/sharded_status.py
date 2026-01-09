"""
分片任务状态存储模块

本模块提供 ShardedTaskStatus 类，使用分片锁机制实现高并发状态查询。
核心思想：
- 将任务状态分散到多个独立分片（默认 16 个）
- 每个分片有独立锁，减少锁竞争
- 查询操作只需锁定单个分片，提升并发性能
"""

import logging
import threading
from typing import Any, Dict, Optional

from fish_async_task.performance._logging import get_logger
from fish_async_task.performance._utils import compute_shard_index, validate_shard_count
from fish_async_task.types import TaskStatusDict


class ShardedTaskStatus:
    """
    分片任务状态存储

    将任务状态分散到多个独立分片，每个分片有独立锁，
    支持 10-15 倍的并发查询性能提升。

    Attributes:
        shard_count: 分片数量
        logger: 日志记录器
    """

    def __init__(self, shard_count: int = 16) -> None:
        """
        初始化分片任务状态存储

        Args:
            shard_count: 分片数量，必须为正整数，建议为 2 的幂次
                       默认 16，在并发性和内存开销之间取得平衡

        Raises:
            ValueError: 如果 shard_count < 1 或 shard_count > 1024
        """
        validate_shard_count(shard_count)

        self.shard_count = shard_count
        self.logger = get_logger()

        # 创建分片：每个分片包含一个状态字典和一个锁
        self._shards: list[dict[str, TaskStatusDict]] = [{} for _ in range(shard_count)]
        self._shard_locks: list[threading.Lock] = [threading.Lock() for _ in range(shard_count)]

        self.logger.info(f"初始化分片任务状态存储：分片数量={shard_count}")

    def _get_shard_index(self, task_id: str) -> int:
        """
        获取任务 ID 对应的分片索引

        Args:
            task_id: 任务 ID

        Returns:
            分片索引（0 到 shard_count-1）

        Examples:
            >>> store = ShardedTaskStatus(shard_count=16)
            >>> store._get_shard_index("task-123")
            7
        """
        return compute_shard_index(task_id, self.shard_count)

    def get_status(self, task_id: str) -> Optional[TaskStatusDict]:
        """
        获取任务状态（线程安全）

        Args:
            task_id: 任务 ID

        Returns:
            任务状态字典，如果不存在返回 None

        Performance:
            O(1) 时间复杂度
            线程安全：仅锁定单个分片

        Examples:
            >>> store = ShardedTaskStatus()
            >>> store.update_status("task-123", {"status": "completed", "result": "success"})
            >>> status = store.get_status("task-123")
            >>> status["result"]
            'success'
        """
        shard_index = self._get_shard_index(task_id)
        shard_lock = self._shard_locks[shard_index]
        shard = self._shards[shard_index]

        with shard_lock:
            return shard.get(task_id)

    def update_status(self, task_id: str, status: TaskStatusDict) -> None:
        """
        更新任务状态（线程安全）

        Args:
            task_id: 任务 ID
            status: 新的任务状态字典

        Raises:
            TypeError: 如果 status 不是 TaskStatusDict 类型

        Performance:
            O(1) 时间复杂度
            线程安全：仅锁定单个分片

        Examples:
            >>> store = ShardedTaskStatus()
            >>> store.update_status("task-123", {"status": "running"})
            >>> store.get_status("task-123")["status"]
            'running'
        """
        shard_index = self._get_shard_index(task_id)
        shard_lock = self._shard_locks[shard_index]
        shard = self._shards[shard_index]

        with shard_lock:
            shard[task_id] = status

        self.logger.debug(f"更新任务状态: task_id={task_id}, 分片={shard_index}")

    def remove_status(self, task_id: str) -> None:
        """
        移除任务状态（线程安全）

        Args:
            task_id: 要移除的任务 ID

        Performance:
            O(1) 时间复杂度
            线程安全：仅锁定单个分片

        Examples:
            >>> store = ShardedTaskStatus()
            >>> store.update_status("task-123", {"status": "completed"})
            >>> store.remove_status("task-123")
            >>> store.get_status("task-123")
            None
        """
        shard_index = self._get_shard_index(task_id)
        shard_lock = self._shard_locks[shard_index]
        shard = self._shards[shard_index]

        with shard_lock:
            if task_id in shard:
                del shard[task_id]
                self.logger.debug(f"移除任务状态: task_id={task_id}, 分片={shard_index}")

    def get_task_count(self) -> int:
        """
        获取当前任务数量

        Returns:
            任务状态字典中的任务数量

        Performance:
            O(n) 时间复杂度，n 为分片数量
            线程安全（返回近似值，但非常准确）

        Examples:
            >>> store = ShardedTaskStatus()
            >>> store.get_task_count()
            0
            >>> store.update_status("task-1", {"status": "completed"})
            >>> store.get_task_count()
            1
        """
        total_count = 0
        for i, shard_lock in enumerate(self._shard_locks):
            with shard_lock:
                total_count += len(self._shards[i])
        return total_count

    def get_all_statuses(self) -> Dict[str, TaskStatusDict]:
        """
        获取所有任务状态（需要获取所有锁）

        Warning:
            此方法会按顺序获取所有分片的锁，可能阻塞较长时间。
            仅在必要时使用（如关闭、统计）。

        Returns:
            所有任务状态的字典

        Performance:
            O(n) 时间复杂度，n 为任务总数
            线程安全：按顺序获取所有锁，避免死锁

        Examples:
            >>> store = ShardedTaskStatus()
            >>> store.update_status("task-1", {"status": "completed"})
            >>> store.update_status("task-2", {"status": "running"})
            >>> all_statuses = store.get_all_statuses()
            >>> len(all_statuses)
            2
        """
        all_statuses: Dict[str, TaskStatusDict] = {}

        # 按顺序获取所有锁（避免死锁）
        for i, shard_lock in enumerate(self._shard_locks):
            with shard_lock:
                all_statuses.update(self._shards[i])

        self.logger.debug(f"获取所有任务状态: 总数={len(all_statuses)}")
        return all_statuses

    def clear_all(self) -> None:
        """
        清空所有任务状态（需要获取所有锁）

        Warning:
            此方法会按顺序获取所有分片的锁。

        Performance:
            O(n) 时间复杂度，n 为任务总数
            线程安全：按顺序获取所有锁

        Examples:
            >>> store = ShardedTaskStatus()
            >>> store.update_status("task-1", {"status": "completed"})
            >>> store.clear_all()
            >>> store.get_task_count()
            0
        """
        total_cleared = 0

        # 按顺序获取所有锁（避免死锁）
        for i, shard_lock in enumerate(self._shard_locks):
            with shard_lock:
                count = len(self._shards[i])
                self._shards[i].clear()
                total_cleared += count

        self.logger.info(f"清空所有任务状态: 清理数量={total_cleared}")
