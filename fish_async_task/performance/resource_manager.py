"""
任务资源管理模块

提供任务资源跟踪和清理功能，防止资源泄漏。
"""

import logging
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Set


class TaskResource:
    """任务资源封装"""

    def __init__(
        self,
        resource_id: str,
        resource: Any,
        cleanup_func: Optional[Callable[[], None]] = None,
    ):
        """
        初始化任务资源

        Args:
            resource_id: 资源唯一标识
            resource: 资源对象
            cleanup_func: 资源清理函数（可选）
        """
        self.resource_id = resource_id
        self.resource = resource
        self.cleanup_func = cleanup_func
        self.created_at = time.time()
        self.last_used = time.time()

    def update_last_used(self) -> None:
        """更新最后使用时间"""
        self.last_used = time.time()

    def cleanup(self) -> bool:
        """
        清理资源

        Returns:
            bool: 清理是否成功
        """
        if self.cleanup_func:
            try:
                self.cleanup_func()
                return True
            except Exception as e:
                logging.warning(f"资源清理函数执行失败 [{self.resource_id}]: {e}")
                return False
        return False


class TaskResourceManager:
    """任务资源管理器 - 跟踪和管理任务相关资源"""

    MAX_TRACKED_RESOURCES = 10000
    DEFAULT_CLEANUP_TIMEOUT = 2.0

    def __init__(
        self,
        logger: logging.Logger = None,
        max_tracked: int = MAX_TRACKED_RESOURCES,
    ):
        """
        初始化任务资源管理器

        Args:
            logger: 日志记录器
            max_tracked: 最大跟踪资源数
        """
        self.logger = logger or logging.getLogger(__name__)
        self._max_tracked = max_tracked

        self._resources: Dict[str, TaskResource] = {}
        self._task_resources: Dict[str, Set[str]] = {}
        self._lock = threading.Lock()

        self._cleanup_queue: deque = deque(maxlen=1000)
        self._cleanup_thread: Optional[threading.Thread] = None
        self._running = threading.Event()

    def start(self) -> None:
        """启动资源清理线程"""
        if self._running.is_set():
            return

        self._running.set()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            name="TaskResourceCleanup",
            daemon=True,
        )
        self._cleanup_thread.start()
        self.logger.debug("任务资源清理线程已启动")

    def stop(self, timeout: float = DEFAULT_CLEANUP_TIMEOUT) -> None:
        """
        停止资源清理线程

        Args:
            timeout: 等待超时时间（秒）
        """
        if not self._running.is_set():
            return

        self._running.clear()

        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=timeout)
            if self._cleanup_thread.is_alive():
                self.logger.warning("资源清理线程在超时后仍未退出")

    def register_resource(
        self,
        task_id: str,
        resource_id: str,
        resource: Any,
        cleanup_func: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        注册任务资源

        Args:
            task_id: 任务ID
            resource_id: 资源唯一标识
            resource: 资源对象
            cleanup_func: 资源清理函数（可选）
        """
        with self._lock:
            task_resource = TaskResource(resource_id, resource, cleanup_func)

            if len(self._resources) >= self._max_tracked:
                self._evict_oldest_resources(count=100)

            self._resources[resource_id] = task_resource

            if task_id not in self._task_resources:
                self._task_resources[task_id] = set()
            self._task_resources[task_id].add(resource_id)

    def unregister_resource(self, resource_id: str) -> bool:
        """
        注销资源

        Args:
            resource_id: 资源唯一标识

        Returns:
            bool: 是否成功注销
        """
        with self._lock:
            if resource_id not in self._resources:
                return False

            resource = self._resources[resource_id]
            resource.cleanup()

            for task_id, resources in self._task_resources.items():
                resources.discard(resource_id)

            del self._resources[resource_id]
            return True

    def register_task(self, task_id: str) -> None:
        """
        注册任务（用于跟踪）

        Args:
            task_id: 任务ID
        """
        with self._lock:
            if task_id not in self._task_resources:
                self._task_resources[task_id] = set()

    def cleanup_task_resources(self, task_id: str, timeout: float = DEFAULT_CLEANUP_TIMEOUT) -> int:
        """
        清理任务的所有资源

        Args:
            task_id: 任务ID
            timeout: 等待超时时间（秒）

        Returns:
            int: 清理的资源数量
        """
        with self._lock:
            if task_id not in self._task_resources:
                return 0

            resource_ids = self._task_resources[task_id]
            cleaned_count = 0

            for resource_id in list(resource_ids):
                if resource_id in self._resources:
                    resource = self._resources[resource_id]

                    if timeout > 0:
                        cleanup_thread = threading.Thread(
                            target=resource.cleanup,
                            daemon=True,
                        )
                        cleanup_thread.start()
                        cleanup_thread.join(timeout=timeout)
                    else:
                        resource.cleanup()

                    del self._resources[resource_id]
                    cleaned_count += 1

            del self._task_resources[task_id]
            return cleaned_count

    def force_cleanup_task(self, task_id: str) -> int:
        """
        强制清理任务资源（不使用线程）

        Args:
            task_id: 任务ID

        Returns:
            int: 清理的资源数量
        """
        with self._lock:
            if task_id not in self._task_resources:
                return 0

            resource_ids = self._task_resources[task_id]
            cleaned_count = 0

            for resource_id in list(resource_ids):
                if resource_id in self._resources:
                    try:
                        self._resources[resource_id].cleanup()
                    except Exception as e:
                        self.logger.warning(
                            f"资源清理失败 [{resource_id}]: {e}"
                        )

                    del self._resources[resource_id]
                    cleaned_count += 1

            del self._task_resources[task_id]
            return cleaned_count

    def _evict_oldest_resources(self, count: int = 100) -> None:
        """驱逐最旧的资源"""
        if not self._resources:
            return

        sorted_resources = sorted(
            self._resources.items(),
            key=lambda x: x[1].last_used,
        )

        evicted = 0
        for resource_id, resource in sorted_resources:
            if evicted >= count:
                break

            resource.cleanup()
            del self._resources[resource_id]
            evicted += 1

            for task_id, resources in self._task_resources.items():
                resources.discard(resource_id)

        if evicted > 0:
            self.logger.debug(f"驱逐了 {evicted} 个过期资源")

    def _cleanup_loop(self) -> None:
        """资源清理循环"""
        while self._running.is_set():
            try:
                self._perform_cleanup()
                time.sleep(1.0)
            except Exception as e:
                self.logger.error(f"资源清理循环异常: {e}")

    def _perform_cleanup(self) -> int:
        """
        执行资源清理

        Returns:
            int: 清理的资源数量
        """
        cleaned_count = 0
        now = time.time()

        with self._lock:
            expired_resources = [
                (rid, r)
                for rid, r in self._resources.items()
                if now - r.last_used > 3600
            ]

            for resource_id, resource in expired_resources[:100]:
                try:
                    resource.cleanup()
                except Exception as e:
                    self.logger.warning(
                        f"资源清理失败 [{resource_id}]: {e}"
                    )

                del self._resources[resource_id]
                cleaned_count += 1

                for task_id in self._task_resources:
                    self._task_resources[task_id].discard(resource_id)

        return cleaned_count

    def get_resource_count(self) -> int:
        """
        获取当前跟踪的资源数量

        Returns:
            int: 资源数量
        """
        with self._lock:
            return len(self._resources)

    def get_task_resource_count(self, task_id: str) -> int:
        """
        获取任务的资源数量

        Args:
            task_id: 任务ID

        Returns:
            int: 资源数量
        """
        with self._lock:
            if task_id not in self._task_resources:
                return 0
            return len(self._task_resources[task_id])

    def get_stats(self) -> Dict[str, Any]:
        """
        获取资源管理统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        with self._lock:
            return {
                "total_resources": len(self._resources),
                "tracked_tasks": len(self._task_resources),
                "max_tracked": self._max_tracked,
                "cleanup_queue_size": len(self._cleanup_queue),
            }


class TimeoutTaskTracker:
    """超时任务跟踪器 - 跟踪并管理超时任务"""

    DEFAULT_TASK_EXPIRY = 3600

    def __init__(
        self,
        logger: logging.Logger = None,
        max_tracked: int = 1000,
        task_expiry: int = DEFAULT_TASK_EXPIRY,
    ):
        """
        初始化超时任务跟踪器

        Args:
            logger: 日志记录器
            max_tracked: 最大跟踪任务数
            task_expiry: 任务信息过期时间（秒）
        """
        self.logger = logger or logging.getLogger(__name__)
        self._max_tracked = max_tracked
        self._task_expiry = task_expiry

        self._timed_out_tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def track_timeout_task(
        self,
        task_id: str,
        thread: threading.Thread,
        submit_time: float = None,
    ) -> None:
        """
        跟踪超时任务

        Args:
            task_id: 任务ID
            thread: 任务执行线程
            submit_time: 任务提交时间
        """
        with self._lock:
            if len(self._timed_out_tasks) >= self._max_tracked:
                self._cleanup_expired()

            self._timed_out_tasks[task_id] = {
                "thread": thread,
                "submit_time": submit_time or time.time(),
                "timeout_time": time.time(),
            }

            self.logger.debug(f"跟踪超时任务: {task_id}")

    def untrack_task(self, task_id: str) -> bool:
        """
        取消跟踪任务

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否成功取消跟踪
        """
        with self._lock:
            if task_id in self._timed_out_tasks:
                del self._timed_out_tasks[task_id]
                return True
            return False

    def _cleanup_expired(self) -> int:
        """清理过期任务记录"""
        now = time.time()
        expired = [
            tid
            for tid, info in self._timed_out_tasks.items()
            if now - info["timeout_time"] > self._task_expiry
        ]

        for tid in expired:
            del self._timed_out_tasks[tid]

        return len(expired)

    def get_tracked_count(self) -> int:
        """
        获取跟踪的任务数量

        Returns:
            int: 任务数量
        """
        with self._lock:
            return len(self._timed_out_tasks)

    def get_stats(self) -> Dict[str, Any]:
        """
        获取跟踪器统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        with self._lock:
            return {
                "tracked_tasks": len(self._timed_out_tasks),
                "max_tracked": self._max_tracked,
                "task_expiry_seconds": self._task_expiry,
            }
