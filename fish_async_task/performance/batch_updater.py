"""批量状态更新器

实现批量状态更新功能，减少锁竞争，支持高吞吐量任务提交。
使用 collections.deque 作为更新缓冲区，支持自动和手动刷新。
"""

import threading
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

from fish_async_task.performance._logging import get_logger
from fish_async_task.types import TaskStatusDict


class BatchedStatusUpdater:
    """
    批量状态更新器

    将多个状态更新缓存到缓冲区，然后批量刷新到底层存储，
    减少锁竞争和提高吞吐量。

    Attributes:
        buffer_size: 触发自动刷新的缓冲区大小
        flush_interval: 触发自动刷新的时间间隔（秒）
        underlying_store: 底层任务状态存储（可选，用于测试）

    Examples:
        >>> store = {}
        >>> updater = BatchedStatusUpdater(
        ...     buffer_size=100,
        ...     flush_interval=1.0,
        ...     underlying_store=store
        ... )
        >>> updater.queue_update("task-1", {"status": "running"})
        >>> updater.flush()  # 手动刷新
        1
        >>> updater.close()  # 关闭并刷新所有待处理更新
    """

    def __init__(
        self,
        buffer_size: int = 100,
        flush_interval: float = 1.0,
        underlying_store: Optional[Dict[str, TaskStatusDict]] = None,
    ) -> None:
        """
        初始化批量状态更新器

        Args:
            buffer_size: 触发自动刷新的缓冲区大小，默认 100
            flush_interval: 触发自动刷新的时间间隔（秒），默认 1.0
            underlying_store: 底层任务状态存储（可选，用于测试）

        Raises:
            ValueError: 如果 buffer_size < 1 或 flush_interval <= 0
        """
        if buffer_size < 1:
            raise ValueError(f"buffer_size 必须 >= 1，当前值: {buffer_size}")
        if flush_interval <= 0:
            raise ValueError(f"flush_interval 必须 > 0，当前值: {flush_interval}")

        self.buffer_size = buffer_size
        self.flush_interval = flush_interval

        # 底层存储（可选）
        if underlying_store is not None:
            self._underlying_store = underlying_store
        else:
            self._underlying_store = {}

        # 更新缓冲区：存储 (task_id, status) 元组
        self._buffer: Dict[str, TaskStatusDict] = {}

        # 线程安全锁
        self._queue_lock = threading.Lock()

        # 最后刷新时间
        self._last_flush_time = time.time()

        # 是否已关闭
        self._closed = False

        # 日志记录器
        self.logger = get_logger()

        self.logger.info(
            f"初始化批量状态更新器：buffer_size={buffer_size}, " f"flush_interval={flush_interval}s"
        )

    def queue_update(self, task_id: str, status: TaskStatusDict) -> None:
        """
        将状态更新排队到缓冲区

        如果缓冲区达到 buffer_size，会自动触发刷新。

        Args:
            task_id: 任务 ID
            status: 任务状态字典

        Raises:
            RuntimeError: 如果更新器已关闭

        Thread-Safety:
            线程安全

        Examples:
            >>> updater = BatchedStatusUpdater()
            >>> updater.queue_update("task-1", {"status": "running"})
        """
        if self._closed:
            raise RuntimeError("BatchedStatusUpdater 已关闭，无法接受新更新")

        with self._queue_lock:
            # 检查是否需要自动刷新（基于时间）
            current_time = time.time()
            time_since_last_flush = current_time - self._last_flush_time

            # 如果距离上次刷新超过间隔，先刷新旧数据
            if time_since_last_flush >= self.flush_interval and self._buffer:
                self._flush_unlocked()
                self._last_flush_time = current_time

            # 将更新添加到缓冲区（覆盖同一任务的旧更新）
            self._buffer[task_id] = status

            # 检查是否需要自动刷新（基于大小）
            if len(self._buffer) >= self.buffer_size:
                self._flush_unlocked()
                self._last_flush_time = current_time

    def flush(self) -> int:
        """
        手动刷新缓冲区到底层存储

        Returns:
            刷新的任务数量

        Thread-Safety:
            线程安全

        Examples:
            >>> updater = BatchedStatusUpdater()
            >>> updater.queue_update("task-1", {"status": "running"})
            >>> flushed = updater.flush()
            >>> print(f"刷新了 {flushed} 个任务")
        """
        with self._queue_lock:
            return self._flush_unlocked()

    def _flush_unlocked(self) -> int:
        """
        内部方法：无锁刷新（调用者必须持有 _queue_lock）

        Returns:
            刷新的任务数量
        """
        if not self._buffer:
            return 0

        # 批量更新到底层存储
        flushed_count = 0
        for task_id, status in self._buffer.items():
            self._underlying_store[task_id] = status
            flushed_count += 1

        # 清空缓冲区
        self._buffer.clear()

        if flushed_count > 0:
            self.logger.info(f"批量刷新: 数量={flushed_count}, 缓冲区大小={self.buffer_size}")

        return flushed_count

    def update_sync(self, task_id: str, status: TaskStatusDict) -> None:
        """
        同步更新（立即写入底层存储，不经过缓冲区）

        用于需要立即更新的场景，例如关键状态变更。

        Args:
            task_id: 任务 ID
            status: 任务状态字典

        Raises:
            RuntimeError: 如果更新器已关闭

        Thread-Safety:
            线程安全

        Examples:
            >>> updater = BatchedStatusUpdater()
            >>> updater.update_sync("task-1", {"status": "completed"})
        """
        if self._closed:
            raise RuntimeError("BatchedStatusUpdater 已关闭，无法接受新更新")

        with self._queue_lock:
            # 直接写入底层存储
            self._underlying_store[task_id] = status

    def get_buffer_length(self) -> int:
        """
        获取当前缓冲区长度

        Returns:
            缓冲区中的任务数量

        Thread-Safety:
            线程安全（返回近似值，但非常准确）

        Examples:
            >>> updater = BatchedStatusUpdater()
            >>> updater.queue_update("task-1", {"status": "running"})
            >>> updater.get_buffer_length()
            1
        """
        with self._queue_lock:
            return len(self._buffer)

    def close(self) -> None:
        """
        关闭更新器并刷新所有待处理的更新

        关闭后不再接受新更新，但会确保所有已排队的更新都被刷新。

        Thread-Safety:
            线程安全

        Examples:
            >>> updater = BatchedStatusUpdater()
            >>> updater.queue_update("task-1", {"status": "running"})
            >>> updater.close()  # 刷新所有待处理更新并关闭
        """
        with self._queue_lock:
            if not self._closed:
                # 刷新所有待处理的更新
                self._flush_unlocked()
                self._closed = True
                self.logger.info("批量状态更新器已关闭")
