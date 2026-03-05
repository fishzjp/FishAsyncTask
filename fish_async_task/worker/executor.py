"""
任务执行器模块

负责任务的实际执行，包括超时控制和状态更新。
"""

import logging
import queue
import threading
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from ..types import TaskStatus, TaskTuple


class TaskExecutor:
    """
    任务执行器

    负责任务的实际执行，包括超时控制和状态更新。
    每个任务在独立的工作线程中执行，支持超时机制。

    线程安全说明：
    - execute_task方法可以在多个线程中并发调用
    - 任务执行是独立的，不会相互影响
    - 超时机制使用daemon线程实现，超时后任务线程仍在后台运行
    - 通过 cleanup_timed_out_tasks 方法可以清理超时的任务线程引用
    """

    # 超时任务跟踪相关常量
    MAX_TRACKED_TIMEOUTS = 1000  # 最多跟踪的超时任务数量
    TIMEOUT_TASK_EXPIRY = 3600  # 超时任务信息过期时间（秒）

    # 批量状态更新相关常量
    BATCH_SIZE = 100  # 批量更新大小
    BATCH_FLUSH_INTERVAL = 0.1  # 批量刷新间隔（秒）

    def __init__(
        self,
        logger: logging.Logger,
        task_timeout_getter: Callable[[], Optional[float]],
        update_status_func: Callable[..., None],
        batch_size: Optional[int] = None,
        batch_flush_interval: Optional[float] = None,
    ):
        """
        初始化任务执行器

        Args:
            logger: 日志记录器
            task_timeout_getter: 获取任务超时时间的函数（支持动态获取）
            update_status_func: 状态更新函数
            batch_size: 批量更新大小（可选，默认使用类常量）
            batch_flush_interval: 批量刷新间隔（秒）（可选，默认使用类常量）
        """
        self.logger = logger
        self._get_task_timeout = task_timeout_getter
        self._update_status = update_status_func

        # 批量状态更新配置
        self._batch_size = batch_size if batch_size is not None else self.BATCH_SIZE
        self._batch_flush_interval = (
            batch_flush_interval if batch_flush_interval is not None else self.BATCH_FLUSH_INTERVAL
        )

        # 批量状态更新队列
        self._batch_updates: deque = deque()
        self._batch_lock = threading.Lock()
        self._last_batch_flush = time.time()

        # 超时任务跟踪（用于资源清理）
        self._timed_out_tasks: Dict[str, float] = {}
        self._timed_out_tasks_lock = threading.Lock()

        # 清理回调列表（用于自定义清理逻辑）
        self._cleanup_callbacks: List[Callable[[str], None]] = []

    def _queue_status_update(
        self,
        task_id: str,
        status: TaskStatus,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        result: Any = None,
        error: Optional[str] = None,
    ) -> None:
        """
        将状态更新添加到批量队列

        Args:
            task_id: 任务ID
            status: 任务状态
            start_time: 任务开始时间（可选）
            end_time: 任务结束时间（可选）
            result: 任务执行结果（可选）
            error: 错误信息（可选）
        """
        update_item = (task_id, status, start_time, end_time, result, error)

        with self._batch_lock:
            self._batch_updates.append(update_item)

            # 检查是否需要刷新
            current_time = time.time()
            time_since_last_flush = current_time - self._last_batch_flush

            # 如果批量大小达到阈值或超过刷新间隔，立即刷新
            if (
                len(self._batch_updates) >= self._batch_size
                or time_since_last_flush >= self._batch_flush_interval
            ):
                self._last_batch_flush = current_time
                self._flush_batch_updates()

    def _flush_batch_updates(self) -> None:
        """刷新批量更新（需要在 batch_lock 保护下调用）"""
        if not self._batch_updates:
            return

        # 获取批量数据（在锁保护下）
        batch_data = list(self._batch_updates)
        self._batch_updates.clear()

        # 释放锁后执行更新
        # 注意：这里假设调用者已经持有锁
        try:
            for task_id, status, start_time, end_time, result, error in batch_data:
                try:
                    self._update_status(
                        task_id,
                        status,
                        start_time=start_time,
                        end_time=end_time,
                        result=result,
                        error=error,
                    )
                except Exception as e:
                    self.logger.error(
                        f"批量更新任务状态失败 [{type(e).__name__}]: {e}", exc_info=True
                    )
        except Exception:
            # 如果执行更新出错，重新将数据放回队列
            with self._batch_lock:
                self._batch_updates.extend(batch_data)
            raise

    def _check_and_flush_batch(self) -> None:
        """检查是否需要刷新批量更新（基于时间间隔）"""
        with self._batch_lock:
            if not self._batch_updates:
                return

            if time.time() - self._last_batch_flush >= self._batch_flush_interval:
                self._flush_batch_updates()

    def flush_pending_updates(self) -> int:
        """
        强制刷新所有待处理的批量更新

        Returns:
            int: 刷新前队列中的更新数量
        """
        with self._batch_lock:
            pending_count = len(self._batch_updates)
            if pending_count > 0:
                self._flush_batch_updates()
            return pending_count

    def get_pending_update_count(self) -> int:
        """
        获取当前待处理的批量更新数量

        Returns:
            int: 待处理的更新数量
        """
        with self._batch_lock:
            return len(self._batch_updates)

    def execute_task(self, task: TaskTuple) -> None:
        """
        执行任务

        Args:
            task: 任务元组，包含(task_id, func, args, kwargs)
        """
        task_id, func, args, kwargs = task
        start_time = time.time()

        try:
            # 更新任务状态为running（使用批量队列）
            self._queue_status_update(task_id, "running", start_time=start_time)
            self.logger.debug("任务 %s 开始执行", task_id)

            # 执行任务（支持超时）
            result = self._execute_with_timeout(task_id, func, args, kwargs)

            # 更新任务状态为completed（使用批量队列）
            end_time = time.time()
            self._queue_status_update(
                task_id, "completed", start_time=start_time, end_time=end_time, result=result
            )
            self.logger.debug("任务 %s 执行完成，耗时 %.2f秒", task_id, end_time - start_time)

        except KeyboardInterrupt:
            # 键盘中断，标记为失败
            end_time = time.time()
            self._queue_status_update(
                task_id, "failed", start_time=start_time, end_time=end_time, error="任务被中断"
            )
            self.logger.warning(f"任务 {task_id} 被中断")
            raise
        except SystemExit:
            # 系统退出，重新抛出
            raise
        except TimeoutError as e:
            # 超时异常，标记为失败
            end_time = time.time()
            self._queue_status_update(
                task_id, "failed", start_time=start_time, end_time=end_time, error=str(e)
            )
            self.logger.warning(f"任务 {task_id} 执行超时: {e}")
        except (IOError, OSError, ConnectionError) as e:
            # I/O 相关异常，可能是临时性问题
            end_time = time.time()
            self._queue_status_update(
                task_id, "failed", start_time=start_time, end_time=end_time, error=str(e)
            )
            self.logger.warning(f"任务 {task_id} 遇到 I/O 异常 [{type(e).__name__}]: {e}")
        except (MemoryError, ResourceWarning) as e:
            # 资源相关异常
            end_time = time.time()
            self._queue_status_update(
                task_id, "failed", start_time=start_time, end_time=end_time, error=str(e)
            )
            self.logger.error(
                f"任务 {task_id} 遇到资源异常 [{type(e).__name__}]: {e}", exc_info=True
            )
        except Exception as e:
            # 记录任务执行异常
            end_time = time.time()
            self._queue_status_update(
                task_id, "failed", start_time=start_time, end_time=end_time, error=str(e)
            )
            error_type = type(e).__name__
            self.logger.error(f"任务 {task_id} 执行失败 [{error_type}]: {e}", exc_info=True)
        finally:
            # 尝试刷新批量更新（基于时间间隔）
            self._check_and_flush_batch()

    def _execute_with_timeout(
        self,
        task_id: str,
        func: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
    ) -> Any:
        """
        执行任务，支持超时控制

        Args:
            task_id: 任务ID
            func: 要执行的任务函数
            args: 任务函数的 positional 参数
            kwargs: 任务函数的关键字参数

        Returns:
            Any: 任务执行结果

        Raises:
            TimeoutError: 任务执行超时
            Exception: 任务执行过程中的异常

        Note:
            Python的线程无法被强制终止，超时后任务线程仍会继续运行。
            这是Python GIL的限制，超时只是停止等待结果，但任务本身可能仍在执行。
            如果需要真正的任务取消，考虑使用进程池或支持取消的第三方库。

        Warning:
            当任务超时时，虽然会抛出TimeoutError，但任务线程仍在后台运行。
            这可能导致资源泄漏（文件句柄、网络连接等）。建议任务函数内部
            实现超时检查机制，或使用支持取消的异步框架。

        资源泄漏预防建议：
        1. 在任务函数中使用上下文管理器（with语句）管理资源
        2. 在任务函数中定期检查超时标志
        3. 使用支持取消的异步框架（如 asyncio）
        4. 对于长时间运行的任务，考虑使用进程池而非线程池
        """
        task_timeout = self._get_task_timeout()
        if not task_timeout:
            return func(*args, **kwargs)

        result_container = self._create_result_container()
        task_thread = self._create_and_start_task_thread(func, args, kwargs, result_container)
        self._wait_for_task_completion(task_thread, task_timeout, task_id, result_container)

        if result_container["exception"]:
            raise result_container["exception"]

        return result_container["result"]

    def _create_result_container(self) -> Dict[str, Any]:
        """创建结果容器"""
        return {
            "result": None,
            "exception": None,
            "completed": False,
        }

    def _create_and_start_task_thread(
        self,
        func: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        result_container: Dict[str, Any],
    ) -> threading.Thread:
        """创建并启动任务线程"""
        def task_wrapper() -> None:
            """任务包装器，捕获执行结果和异常"""
            try:
                result_container["result"] = func(*args, **kwargs)
            except Exception as e:
                result_container["exception"] = e
            finally:
                result_container["completed"] = True

        task_thread = threading.Thread(target=task_wrapper, daemon=True)
        task_thread.start()
        return task_thread

    def _wait_for_task_completion(
        self,
        task_thread: threading.Thread,
        task_timeout: float,
        task_id: str,
        result_container: Dict[str, Any],
    ) -> None:
        """等待任务完成或超时"""
        task_thread.join(timeout=task_timeout)

        if not result_container["completed"]:
            self._handle_task_timeout(task_id, task_timeout)

    def _handle_task_timeout(self, task_id: str, task_timeout: float) -> None:
        """处理任务超时"""
        self.logger.warning(
            f"任务 {task_id} 执行超时（{task_timeout}秒），"
            f"但任务线程仍在后台运行，可能导致资源泄漏"
        )

        self._track_timed_out_task(task_id)
        self._trigger_cleanup_callbacks(task_id)

        raise TimeoutError(f"任务 {task_id} 执行超时（{task_timeout}秒）")

    def _track_timed_out_task(self, task_id: str) -> None:
        """跟踪超时任务"""
        current_time = time.time()

        with self._timed_out_tasks_lock:
            # 清理过期的超时任务记录
            expired_tasks = [
                tid
                for tid, expiry in self._timed_out_tasks.items()
                if current_time - expiry > self.TIMEOUT_TASK_EXPIRY
            ]
            for tid in expired_tasks:
                self._timed_out_tasks.pop(tid, None)

            # 添加新的超时任务记录
            if len(self._timed_out_tasks) < self.MAX_TRACKED_TIMEOUTS:
                self._timed_out_tasks[task_id] = current_time

    def add_cleanup_callback(self, callback: Callable[[str], None]) -> None:
        """
        添加清理回调函数

        当任务超时时，会调用所有注册的清理回调函数。

        Args:
            callback: 清理回调函数，接收任务ID作为参数
        """
        with self._timed_out_tasks_lock:
            self._cleanup_callbacks.append(callback)

    def _trigger_cleanup_callbacks(self, task_id: str) -> None:
        """
        触发所有清理回调

        Args:
            task_id: 超时的任务ID
        """
        for callback in self._cleanup_callbacks:
            try:
                callback(task_id)
            except Exception as e:
                self.logger.error(f"清理回调执行失败 [{type(e).__name__}]: {e}", exc_info=True)

    def cleanup_timed_out_tasks(self, max_cleanup: int = 100) -> int:
        """
        清理超时的任务线程引用

        注意：由于Python线程无法被强制终止，此方法主要用于清理跟踪信息，
        实际的任务线程仍会在后台运行直到任务完成或进程退出。

        Args:
            max_cleanup: 最大清理数量

        Returns:
            int: 清理的任务数量
        """
        current_time = time.time()
        cleaned_count = 0

        with self._timed_out_tasks_lock:
            expired_tasks = [
                (tid, expiry)
                for tid, expiry in self._timed_out_tasks.items()
                if current_time - expiry > self.TIMEOUT_TASK_EXPIRY
            ]

            # 限制每次清理的数量
            for task_id, _ in expired_tasks[:max_cleanup]:
                self._timed_out_tasks.pop(task_id, None)
                cleaned_count += 1

        if cleaned_count > 0:
            self.logger.info(f"清理了 {cleaned_count} 个超时任务跟踪记录")

        return cleaned_count

    def get_timed_out_task_count(self) -> int:
        """
        获取当前跟踪的超时任务数量

        Returns:
            int: 超时任务数量
        """
        with self._timed_out_tasks_lock:
            return len(self._timed_out_tasks)
