"""
优先级队列清理模块

本模块提供 TaskStatusWithExpiry 类，使用优先级队列（最小堆）
跟踪任务过期时间，支持高效的增量清理操作。
核心思想：
- 使用 heapq 维护 (expiry_time, task_id) 的最小堆
- 清理操作只处理已过期的任务，复杂度 O(k log n)
- 增量清理避免长时间阻塞
"""

import heapq
import logging
import threading
import time
from typing import Any, Dict, Optional

from fish_async_task.performance._logging import get_logger
from fish_async_task.performance._utils import compute_expiry_time
from fish_async_task.types import TaskStatusDict


class TaskStatusWithExpiry:
    """
    带过期时间的任务状态存储

    使用优先级队列（最小堆）跟踪任务过期时间，
    支持高效的增量清理操作。

    Attributes:
        ttl: 任务状态生存时间（秒）
        logger: 日志记录器
    """

    def __init__(self, ttl: int = 300) -> None:
        """
        初始化带过期时间的任务状态存储

        Args:
            ttl: 任务状态生存时间（秒），默认 300（5 分钟）

        Note:
            清理操作会移除超过 TTL 的任务状态
        """
        if ttl < 1:
            raise ValueError(f"ttl 必须 >= 1，当前值: {ttl}")

        self.ttl = ttl
        self.logger = get_logger()

        # 任务状态字典
        self.status_dict: Dict[str, TaskStatusDict] = {}

        # 优先级队列（最小堆）：存储 (expiry_time, task_id)
        self.expiry_heap: list[tuple[float, str]] = []

        # 优先级队列的锁
        self.heap_lock = threading.Lock()

        self.logger.info(f"初始化优先级队列清理存储：TTL={ttl}秒")

    def add_task(self, task_id: str, status: TaskStatusDict) -> None:
        """
        添加任务状态

        Args:
            task_id: 任务 ID
            status: 任务状态字典，必须包含 end_time 字段

        Behavior:
            - 将任务添加到 status_dict
            - 如果有 end_time，计算过期时间并添加到优先级队列

        Raises:
            ValueError: 如果 status 不包含 end_time

        Examples:
            >>> store = TaskStatusWithExpiry(ttl=300)
            >>> store.add_task("task-123", {
            ...     "task_id": "task-123",
            ...     "status": "completed",
            ...     "end_time": time.time()
            ... })
        """
        with self.heap_lock:
            # 添加到状态字典
            self.status_dict[task_id] = status

            # 如果有 end_time，添加到优先级队列
            end_time = status.get("end_time")
            if end_time is not None:
                expiry_time = compute_expiry_time(end_time, self.ttl)
                heapq.heappush(self.expiry_heap, (expiry_time, task_id))
                self.logger.debug(
                    f"添加任务到优先级队列: task_id={task_id}, expiry_time={expiry_time}"
                )

    def get_task(self, task_id: str) -> Optional[TaskStatusDict]:
        """
        获取任务状态

        Args:
            task_id: 任务 ID

        Returns:
            任务状态字典，如果不存在返回 None

        Note:
            此方法不锁定优先级队列（只读操作）
        """
        with self.heap_lock:
            return self.status_dict.get(task_id)

    def cleanup_expired(self, max_cleanup: Optional[int] = None) -> int:
        """
        清理过期任务（增量清理）

        Args:
            max_cleanup: 最大清理数量，None 表示清理所有过期任务
                        默认 None

        Returns:
            清理的任务数量

        Performance:
            O(k log n) 时间复杂度，k 为过期任务数量
            通常 k << n，因此远快于全量扫描 O(n)

        Thread-Safety:
            线程安全，使用 heap_lock 保护

        Note:
            增量清理：每次最多清理 max_cleanup 个任务，
            避免长时间阻塞其他操作

        Examples:
            >>> store = TaskStatusWithExpiry(ttl=300)
            >>> # 添加过期任务...
            >>> cleaned_count = store.cleanup_expired(max_cleanup=100)
            >>> print(f"清理了 {cleaned_count} 个过期任务")
        """
        with self.heap_lock:
            cleaned_count = 0
            current_time = time.time()

            # 清理过期任务
            while self.expiry_heap:
                # 检查是否达到最大清理数量
                if max_cleanup is not None and cleaned_count >= max_cleanup:
                    break

                # 查看堆顶元素（最早过期的任务）
                expiry_time, task_id = self.expiry_heap[0]

                # 如果堆顶任务未过期，则后续任务都未过期
                if expiry_time > current_time:
                    break

                # 弹出堆顶元素
                heapq.heappop(self.expiry_heap)

                # 从状态字典中删除（如果存在）
                if task_id in self.status_dict:
                    # 验证确实已过期（双重检查）
                    status = self.status_dict[task_id]
                    status_end_time: Optional[float] = status.get("end_time")
                    if status_end_time is not None and current_time - status_end_time > self.ttl:
                        del self.status_dict[task_id]
                        cleaned_count += 1

            if cleaned_count > 0:
                self.logger.info(f"清理过期任务: 数量={cleaned_count}, max_cleanup={max_cleanup}")

            return cleaned_count

    def enforce_max_count(self, max_count: int) -> int:
        """
        强制执行最大任务数量限制

        当任务数量超过 max_count 时，删除最旧的任务（按 submit_time 或 start_time）。

        Args:
            max_count: 最大任务数量

        Returns:
            删除的任务数量

        Performance:
            O(n log n) 时间复杂度，n 为任务总数

        Thread-Safety:
            线程安全，使用 heap_lock 保护

        Examples:
            >>> store = TaskStatusWithExpiry(ttl=300)
            >>> # 添加大量任务...
            >>> removed_count = store.enforce_max_count(max_count=10000)
            >>> print(f"移除了 {removed_count} 个旧任务")
        """
        with self.heap_lock:
            current_count = len(self.status_dict)

            if current_count <= max_count:
                return 0

            # 需要删除的任务数量
            to_remove = current_count - max_count

            # 收集所有任务及其时间戳
            tasks_with_time = []
            for task_id, status in self.status_dict.items():
                # 优先使用 submit_time，如果没有则使用 start_time，最后使用 end_time
                timestamp = (
                    status.get("submit_time")
                    or status.get("start_time")
                    or status.get("end_time")
                    or 0.0
                )
                tasks_with_time.append((timestamp, task_id))

            # 按时间戳排序（最旧的在前）
            tasks_with_time.sort(key=lambda x: x[0])

            # 收集要删除的 task_id
            to_remove_ids = set(task_id for _, task_id in tasks_with_time[:to_remove])

            # 从 status_dict 中删除
            removed_count = 0
            for task_id in to_remove_ids:
                if task_id in self.status_dict:
                    del self.status_dict[task_id]
                    removed_count += 1

            # 一次性重建堆，排除已删除的 task_id（O(n) 操作）
            self.expiry_heap = [
                (exp_time, tid) for exp_time, tid in self.expiry_heap if tid not in to_remove_ids
            ]
            heapq.heapify(self.expiry_heap)

            if removed_count > 0:
                self.logger.info(
                    f"强制执行最大数量限制: 删除={removed_count}, max_count={max_count}"
                )

            return removed_count

    def get_task_count(self) -> int:
        """
        获取当前任务数量

        Returns:
            任务状态字典中的任务数量

        Performance:
            O(1) 时间复杂度

        Thread-Safety:
            线程安全（返回近似值，但非常准确）

        Examples:
            >>> store = TaskStatusWithExpiry()
            >>> store.add_task("task-123", {"end_time": time.time()})
            >>> store.get_task_count()
            1
        """
        with self.heap_lock:
            return len(self.status_dict)

    def get_all_statuses(self) -> Dict[str, TaskStatusDict]:
        """
        获取所有任务状态

        Returns:
            所有任务状态的字典

        Note:
            此方法会锁定优先级队列，避免在清理期间调用
        """
        with self.heap_lock:
            return dict(self.status_dict)  # 返回副本
