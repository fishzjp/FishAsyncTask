"""
优先级任务队列模块

提供带优先级的任务队列支持。
"""

import heapq
import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


@dataclass(order=True)
class PrioritizedTask:
    """
    带优先级的任务

    优先级数字越小，优先级越高。
    """

    priority: int
    task_id: str = field(compare=False)
    func: Callable = field(compare=False)
    args: tuple = field(compare=False)
    kwargs: dict = field(compare=False)
    submit_time: float = field(compare=False, default_factory=time.time)


class PriorityTaskQueue:
    """优先级任务队列"""

    def __init__(self, maxsize: int = 1000):
        """
        初始化优先级任务队列

        Args:
            maxsize: 队列最大容量，0表示无限制
        """
        self.maxsize = maxsize
        self._queue: List[PrioritizedTask] = []
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._not_full = threading.Condition(self._lock)
        self._task_ids: Set[str] = set()

    def put(
        self,
        task: PrioritizedTask,
        block: bool = True,
        timeout: Optional[float] = None,
    ) -> None:
        """
        添加任务到队列

        Args:
            task: 优先级任务
            block: 是否阻塞
            timeout: 超时时间

        Raises:
            queue.Full: 队列满且阻塞超时
        """
        with self._not_full:
            if self.maxsize > 0:
                if not block:
                    if len(self._queue) >= self.maxsize:
                        raise queue.Full()
                    while len(self._queue) >= self.maxsize:
                        self._not_full.wait(timeout=timeout)
                        if len(self._queue) >= self.maxsize:
                            raise queue.Full()

            heapq.heappush(self._queue, task)
            self._task_ids.add(task.task_id)
            self._not_empty.notify()

    def get(
        self,
        block: bool = True,
        timeout: Optional[float] = None,
    ) -> PrioritizedTask:
        """
        获取最高优先级任务

        Args:
            block: 是否阻塞
            timeout: 超时时间

        Returns:
            PrioritizedTask: 优先级任务

        Raises:
            queue.Empty: 队列空且阻塞超时
        """
        with self._not_empty:
            if not block:
                if not self._queue:
                    raise queue.Empty()
            else:
                while not self._queue:
                    self._not_empty.wait(timeout=timeout)
                    if not self._queue:
                        raise queue.Empty()

            task = heapq.heappop(self._queue)
            self._task_ids.discard(task.task_id)
            self._not_full.notify()
            return task

    def task_done(self) -> None:
        """标记任务完成"""
        with self._not_full:
            self._not_full.notify()

    def qsize(self) -> int:
        """
        获取队列大小

        Returns:
            int: 队列大小
        """
        with self._lock:
            return len(self._queue)

    def empty(self) -> bool:
        """
        检查队列是否为空

        Returns:
            bool: 队列是否为空
        """
        with self._lock:
            return len(self._queue) == 0

    def full(self) -> bool:
        """
        检查队列是否已满

        Returns:
            bool: 队列是否已满
        """
        with self._lock:
            if self.maxsize <= 0:
                return False
            return len(self._queue) >= self.maxsize

    def contains(self, task_id: str) -> bool:
        """
        检查任务是否在队列中

        Args:
            task_id: 任务ID

        Returns:
            bool: 任务是否在队列中
        """
        with self._lock:
            return task_id in self._task_ids

    def remove(self, task_id: str) -> bool:
        """
        从队列中移除任务

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否成功移除
        """
        with self._lock:
            for i, task in enumerate(self._queue):
                if task.task_id == task_id:
                    del self._queue[i]
                    heapq.heapify(self._queue)
                    self._task_ids.discard(task_id)
                    self._not_full.notify()
                    return True
            return False

    def clear(self) -> int:
        """
        清空队列

        Returns:
            int: 清空的任务数量
        """
        with self._lock:
            count = len(self._queue)
            self._queue.clear()
            self._task_ids.clear()
            self._not_full.notify_all()
            return count


class PriorityTaskManager:
    """优先级任务管理器"""

    def __init__(
        self,
        logger: logging.Logger = None,
        maxsize: int = 1000,
    ):
        """
        初始化优先级任务管理器

        Args:
            logger: 日志记录器
            maxsize: 队列最大容量
        """
        self.logger = logger or logging.getLogger(__name__)
        self._queue = PriorityTaskQueue(maxsize=maxsize)
        self._pending_tasks: Dict[str, PrioritizedTask] = {}
        self._lock = threading.Lock()

    def submit_task(
        self,
        func: Callable[..., Any],
        priority: int = 5,
        task_id: Optional[str] = None,
        args: tuple = (),
        kwargs: dict = None,
    ) -> str:
        """
        提交带优先级的任务

        Args:
            func: 任务函数
            priority: 优先级（数字越小优先级越高）
            task_id: 任务ID（可选，默认自动生成）
            args: 位置参数
            kwargs: 关键字参数

        Returns:
            str: 任务ID
        """
        import uuid

        if task_id is None:
            task_id = str(uuid.uuid4())

        if kwargs is None:
            kwargs = {}

        task = PrioritizedTask(
            priority=priority,
            task_id=task_id,
            func=func,
            args=args,
            kwargs=kwargs,
        )

        with self._lock:
            self._pending_tasks[task_id] = task
            self._queue.put(task)

        self.logger.debug(f"提交优先级任务: {task_id}, 优先级: {priority}")
        return task_id

    def get_task(self, timeout: Optional[float] = None) -> Optional[PrioritizedTask]:
        """
        获取最高优先级任务

        Args:
            timeout: 超时时间

        Returns:
            Optional[PrioritizedTask]: 优先级任务
        """
        try:
            task = self._queue.get(timeout=timeout)
            with self._lock:
                self._pending_tasks.pop(task.task_id, None)
            return task
        except queue.Empty:
            return None

    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否成功取消
        """
        with self._lock:
            if task_id in self._pending_tasks:
                self._pending_tasks.pop(task_id, None)
                return self._queue.remove(task_id)
        return False

    def get_queue_size(self) -> int:
        """
        获取队列大小

        Returns:
            int: 队列大小
        """
        return self._queue.qsize()

    def is_empty(self) -> bool:
        """
        检查队列是否为空

        Returns:
            bool: 队列是否为空
        """
        return self._queue.empty()

    def get_pending_count(self) -> int:
        """
        获取待处理任务数量

        Returns:
            int: 待处理任务数量
        """
        with self._lock:
            return len(self._pending_tasks)


class TaskDependencyManager:
    """任务依赖管理器"""

    def __init__(self, logger: logging.Logger = None):
        """
        初始化任务依赖管理器

        Args:
            logger: 日志记录器
        """
        self.logger = logger or logging.getLogger(__name__)
        self._dependencies: Dict[str, Set[str]] = {}
        self._dependents: Dict[str, Set[str]] = {}
        self._completed_tasks: Set[str] = set()
        self._failed_tasks: Set[str] = set()
        self._lock = threading.Lock()

    def add_dependency(
        self,
        task_id: str,
        depends_on: List[str],
    ) -> None:
        """
        添加任务依赖

        Args:
            task_id: 任务ID
            depends_on: 依赖的任务ID列表
        """
        with self._lock:
            if task_id not in self._dependencies:
                self._dependencies[task_id] = set()

            for dep in depends_on:
                self._dependencies[task_id].add(dep)

                if dep not in self._dependents:
                    self._dependents[dep] = set()
                self._dependents[dep].add(task_id)

    def mark_completed(self, task_id: str) -> None:
        """
        标记任务完成

        Args:
            task_id: 任务ID
        """
        with self._lock:
            self._completed_tasks.add(task_id)

            if task_id in self._dependents:
                dependent_tasks = self._dependents[task_id]
                for dependent in dependent_tasks:
                    if dependent in self._dependencies:
                        self._dependencies[dependent].discard(task_id)

    def mark_failed(self, task_id: str) -> None:
        """
        标记任务失败

        Args:
            task_id: 任务ID
        """
        with self._lock:
            self._failed_tasks.add(task_id)

    def _is_ready_locked(self, task_id: str) -> bool:
        """检查任务是否就绪（调用方必须已持有 self._lock）"""
        if task_id not in self._dependencies:
            return True
        return self._dependencies[task_id].issubset(self._completed_tasks)

    def is_ready(self, task_id: str) -> bool:
        """
        检查任务是否就绪（所有依赖已满足）

        Args:
            task_id: 任务ID

        Returns:
            bool: 任务是否就绪
        """
        with self._lock:
            return self._is_ready_locked(task_id)

    def get_ready_tasks(self) -> List[str]:
        """
        获取所有就绪的任务

        Returns:
            List[str]: 就绪的任务ID列表
        """
        with self._lock:
            return [tid for tid in self._dependencies if self._is_ready_locked(tid)]

    def has_circular_dependency(self, task_id: str) -> bool:
        """
        检查是否存在循环依赖

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否存在循环依赖
        """
        visited = set()
        rec_stack = set()

        def _has_cycle(tid: str) -> bool:
            visited.add(tid)
            rec_stack.add(tid)

            if tid in self._dependencies:
                for dep in self._dependencies[tid]:
                    if dep not in visited:
                        if _has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        return True

            rec_stack.remove(tid)
            return False

        return _has_cycle(task_id)

    def clear(self) -> None:
        """清除所有依赖信息"""
        with self._lock:
            self._dependencies.clear()
            self._dependents.clear()
            self._completed_tasks.clear()
            self._failed_tasks.clear()

    def get_stats(self) -> Dict[str, Any]:
        """
        获取依赖管理器统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        with self._lock:
            return {
                "total_tasks": len(self._dependencies),
                "completed_tasks": len(self._completed_tasks),
                "failed_tasks": len(self._failed_tasks),
                "pending_tasks": len(self._dependencies)
                - len(self._completed_tasks)
                - len(self._failed_tasks),
            }
