"""
任务取消模块

提供任务取消功能，支持协作式取消机制。
"""

import logging
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Set


class CancelEvent:
    """取消事件 - 用于协作式任务取消"""

    def __init__(self):
        """初始化取消事件"""
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        """设置取消标志"""
        self._cancelled.set()

    def is_cancelled(self) -> bool:
        """
        检查是否已取消

        Returns:
            bool: 是否已取消
        """
        return self._cancelled.is_set()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """
        等待取消事件

        Args:
            timeout: 超时时间

        Returns:
            bool: 是否在超时前被设置
        """
        return self._cancelled.wait(timeout=timeout)

    def reset(self) -> None:
        """重置取消事件"""
        self._cancelled.clear()


class CancellableTask:
    """可取消的任务封装"""

    def __init__(
        self,
        task_id: str,
        func: Callable[..., Any],
        args: tuple = (),
        kwargs: dict = None,
    ):
        """
        初始化可取消任务

        Args:
            task_id: 任务ID
            func: 任务函数
            args: 位置参数
            kwargs: 关键字参数
        """
        self.task_id = task_id
        self.func = func
        self.args = args
        self.kwargs = kwargs or {}
        self.cancel_event = CancelEvent()
        self._result = None
        self._exception = None
        self._completed = threading.Event()
        self._started = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def execute(self) -> Any:
        """
        执行任务

        Returns:
            Any: 任务执行结果

        Raises:
            Exception: 任务执行过程中的异常
        """
        if self.cancel_event.is_cancelled():
            return None

        self._started.set()

        try:
            result = self.func(
                *self.args,
                cancel_event=self.cancel_event,
                **self.kwargs,
            )
            self._result = result
            return result
        except Exception as e:
            self._exception = e
            raise
        finally:
            self._completed.set()

    def cancel(self, timeout: float = 1.0) -> bool:
        """
        取消任务

        Args:
            timeout: 等待任务停止的超时时间

        Returns:
            bool: 是否成功取消
        """
        if self._completed.is_set():
            return False

        self.cancel_event.cancel()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            return not self._thread.is_alive()

        return True

    def is_completed(self) -> bool:
        """
        检查任务是否完成

        Returns:
            bool: 任务是否完成
        """
        return self._completed.is_set()

    def is_started(self) -> bool:
        """
        检查任务是否已开始

        Returns:
            bool: 任务是否已开始
        """
        return self._started.is_set()

    def get_result(self, timeout: Optional[float] = None) -> Any:
        """
        获取任务结果

        Args:
            timeout: 超时时间

        Returns:
            Any: 任务结果

        Raises:
            Exception: 任务执行过程中的异常
        """
        if not self._completed.wait(timeout=timeout):
            raise TimeoutError(f"等待任务 {self.task_id} 结果超时")

        if self._exception:
            raise self._exception

        return self._result


class TaskCancellationManager:
    """任务取消管理器"""

    def __init__(self, logger: logging.Logger = None):
        """
        初始化任务取消管理器

        Args:
            logger: 日志记录器
        """
        self.logger = logger or logging.getLogger(__name__)
        self._cancellable_tasks: Dict[str, CancellableTask] = {}
        self._cancel_tokens: Dict[str, CancelEvent] = {}
        self._lock = threading.Lock()

    def register_task(
        self,
        task_id: str,
        func: Callable[..., Any],
        args: tuple = (),
        kwargs: dict = None,
    ) -> CancelEvent:
        """
        注册可取消任务

        Args:
            task_id: 任务ID
            func: 任务函数
            args: 位置参数
            kwargs: 关键字参数

        Returns:
            CancelEvent: 取消事件对象
        """
        with self._lock:
            if task_id in self._cancellable_tasks:
                self.logger.warning(f"任务 {task_id} 已存在，将被覆盖")

            task = CancellableTask(task_id, func, args, kwargs)
            self._cancellable_tasks[task_id] = task
            self._cancel_tokens[task_id] = task.cancel_event

            return task.cancel_event

    def cancel_task(self, task_id: str, timeout: float = 1.0) -> bool:
        """
        取消任务

        Args:
            task_id: 任务ID
            timeout: 等待任务停止的超时时间

        Returns:
            bool: 是否成功取消
        """
        with self._lock:
            if task_id not in self._cancellable_tasks:
                return False

            task = self._cancellable_tasks[task_id]
            success = task.cancel(timeout=timeout)

            if success or task.is_completed():
                self._cleanup_task(task_id)

            return success

    def cancel_all(self, timeout: float = 1.0) -> int:
        """
        取消所有任务

        Args:
            timeout: 等待每个任务停止的超时时间

        Returns:
            int: 成功取消的任务数量
        """
        with self._lock:
            cancelled = 0

            for task_id in list(self._cancellable_tasks.keys()):
                task = self._cancellable_tasks[task_id]
                if task.cancel(timeout=timeout):
                    cancelled += 1
                self._cleanup_task(task_id)

            return cancelled

    def _cleanup_task(self, task_id: str) -> None:
        """清理任务记录"""
        self._cancellable_tasks.pop(task_id, None)
        self._cancel_tokens.pop(task_id, None)

    def get_cancel_token(self, task_id: str) -> Optional[CancelEvent]:
        """
        获取任务的取消令牌

        Args:
            task_id: 任务ID

        Returns:
            Optional[CancelEvent]: 取消事件对象
        """
        with self._lock:
            return self._cancel_tokens.get(task_id)

    def is_task_cancelled(self, task_id: str) -> bool:
        """
        检查任务是否已取消

        Args:
            task_id: 任务ID

        Returns:
            bool: 任务是否已取消
        """
        with self._lock:
            if task_id not in self._cancel_tokens:
                return False
            return self._cancel_tokens[task_id].is_cancelled()

    def is_task_completed(self, task_id: str) -> bool:
        """
        检查任务是否已完成

        Args:
            task_id: 任务ID

        Returns:
            bool: 任务是否已完成
        """
        with self._lock:
            if task_id not in self._cancellable_tasks:
                return False
            return self._cancellable_tasks[task_id].is_completed()

    def get_active_count(self) -> int:
        """
        获取活跃任务数量

        Returns:
            int: 活跃任务数量
        """
        with self._lock:
            return len(self._cancellable_tasks)

    def get_stats(self) -> Dict[str, Any]:
        """
        获取取消管理器统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        with self._lock:
            active = 0
            completed = 0

            for task in self._cancellable_tasks.values():
                if task.is_completed():
                    completed += 1
                else:
                    active += 1

            return {
                "total_tracked": len(self._cancellable_tasks),
                "active": active,
                "completed": completed,
            }


def create_cancellable_task(
    func: Callable[..., Any],
    cancel_event: CancelEvent = None,
    *args: Any,
    **kwargs: Any,
) -> Callable[[], Any]:
    """
    创建支持取消检查的任务包装器

    Args:
        func: 原始任务函数
        cancel_event: 取消事件对象
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        Callable[[], Any]: 包装后的任务函数
    """

    def wrapper():
        if cancel_event and cancel_event.is_cancelled():
            return None

        result = func(*args, **kwargs)

        if cancel_event and cancel_event.is_cancelled():
            return None

        return result

    return wrapper


def check_cancelled_periodically(
    cancel_event: CancelEvent,
    check_interval: int = 100,
) -> bool:
    """
    周期性检查取消状态的辅助函数

    可以在长时间运行的任务中定期调用此函数来检查是否被取消。

    Args:
        cancel_event: 取消事件对象
        check_interval: 检查间隔（每N次操作检查一次）

    Returns:
        bool: 是否已取消
    """
    if cancel_event is None:
        return False

    counter = 0
    while counter < check_interval:
        counter += 1
        if counter >= check_interval:
            if cancel_event.is_cancelled():
                return True
            counter = 0

    return cancel_event.is_cancelled()
