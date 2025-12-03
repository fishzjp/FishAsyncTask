"""
工作线程模块

负责工作线程的创建、管理和任务执行。
"""

import threading
import queue
import time
import uuid
import logging
from typing import Any, Callable, Dict, List, Optional

from .types import TaskTuple


class WorkerManager:
    """
    工作线程管理器
    
    负责管理工作线程的生命周期，包括创建、扩展和回收。
    支持动态线程池，根据任务队列大小自动调整线程数量。
    
    线程安全说明：
    - 所有对worker_threads列表的操作都在threads_lock保护下进行
    - 线程退出时会从列表中安全移除，避免竞态条件
    """
    
    def __init__(
        self,
        logger: logging.Logger,
        task_queue: "queue.Queue[TaskTuple]",
        worker_threads: List[threading.Thread],
        threads_lock: threading.Lock,
        running_event: threading.Event,
        min_workers: int,
        max_workers: int,
        idle_timeout: int,
        task_timeout: Optional[float],
        execute_task_func: Callable[[TaskTuple], None],
    ):
        """
        初始化工作线程管理器
        
        Args:
            logger: 日志记录器
            task_queue: 任务队列
            worker_threads: 工作线程列表
            threads_lock: 线程锁
            running_event: 运行事件
            min_workers: 最小工作线程数
            max_workers: 最大工作线程数
            idle_timeout: 空闲超时时间（秒）
            task_timeout: 任务超时时间（秒）
            execute_task_func: 任务执行函数
        """
        self.logger = logger
        self.task_queue = task_queue
        self.worker_threads = worker_threads
        self.threads_lock = threads_lock
        self._running_event = running_event
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.idle_timeout = idle_timeout
        self.task_timeout = task_timeout
        self._execute_task = execute_task_func
    
    def start_initial_workers(self) -> None:
        """
        启动初始工作线程
        
        根据 min_workers 配置启动最小数量的工作线程。
        这些线程会持续运行，不会被空闲超时机制回收。
        """
        for _ in range(self.min_workers):
            thread = threading.Thread(
                target=self._worker_loop,
                name=f"TaskWorker-{uuid.uuid4()}",
                daemon=True,
            )
            thread.start()
            self.worker_threads.append(thread)
        self.logger.info(f"启动初始工作线程数: {len(self.worker_threads)}")
    
    def scale_up_workers_if_needed(self) -> None:
        """
        根据队列大小动态扩展工作线程
        
        当队列中的任务数量超过当前线程数时，自动创建新线程。
        线程数量不会超过 max_workers 限制。
        """
        with self.threads_lock:
            current_thread_count = len(self.worker_threads)
            queue_size = self.task_queue.qsize()
            
            if (
                current_thread_count < self.max_workers
                and queue_size > current_thread_count
            ):
                self._create_and_start_worker()
    
    def _create_and_start_worker(self) -> None:
        """
        创建并启动新的工作线程
        
        注意：此方法应在 threads_lock 保护下调用，或确保调用者已持有锁。
        """
        thread = threading.Thread(
            target=self._worker_loop,
            name=f"TaskWorker-{uuid.uuid4()}",
            daemon=True,
        )
        thread.start()
        self.worker_threads.append(thread)
        self.logger.info(f"启动新工作线程，当前线程数: {len(self.worker_threads)}")
    
    def _worker_loop(self) -> None:
        """
        工作线程主循环
        
        从任务队列中获取任务并执行。当空闲时间超过 idle_timeout 且
        当前线程数大于 min_workers 时，线程会自动退出以节省资源。
        """
        thread_name = threading.current_thread().name
        self.logger.debug(f"工作线程启动: {thread_name}")
        idle_start: Optional[float] = None
        
        while self._running_event.is_set():
            try:
                task = self.task_queue.get(timeout=1)
                
                # 退出信号
                if task is None:
                    self.task_queue.task_done()
                    break
                
                idle_start = None
                self._execute_task(task)
                self.task_queue.task_done()
                
            except queue.Empty:
                now = time.time()
                if idle_start is None:
                    idle_start = now
                elif now - idle_start >= self.idle_timeout:
                    # 检查是否可以退出（保持最小线程数）
                    # 在锁内检查并移除，避免竞态条件
                    with self.threads_lock:
                        current_thread = threading.current_thread()
                        # 再次检查线程数，确保在锁内的一致性
                        if len(self.worker_threads) > self.min_workers:
                            # 检查当前线程是否仍在列表中
                            if current_thread in self.worker_threads:
                                self.worker_threads.remove(current_thread)
                                self.logger.info(f"空闲线程退出: {thread_name}")
                                break
                            # 如果线程不在列表中，说明已被其他操作移除，直接退出
                            else:
                                self.logger.debug(f"线程 {thread_name} 已被移除，退出")
                                break
                continue
                
            except KeyboardInterrupt:
                # 键盘中断，正常退出
                self.logger.info(f"工作线程收到中断信号: {thread_name}")
                break
            except SystemExit:
                # 系统退出，重新抛出，不捕获
                raise
            except queue.Full:
                # 队列满异常，不应该在工作线程中出现，记录警告
                self.logger.warning(f"工作线程意外遇到队列满异常: {thread_name}")
            except Exception as e:
                # 记录未预期的异常，但不中断线程运行
                # 这确保了单个任务的异常不会影响整个线程池的运行
                error_type = type(e).__name__
                self.logger.error(
                    f"工作线程执行异常 [{error_type}]: {e}", exc_info=True
                )
        
        self.logger.debug(f"工作线程退出: {thread_name}")
    
    def send_shutdown_signals(self) -> None:
        """
        向所有工作线程发送退出信号
        
        通过向任务队列中放入 None 值来通知工作线程退出。
        如果队列已满，会尝试等待并重试。
        """
        with self.threads_lock:
            thread_count = len(self.worker_threads)
        
        # 尝试发送退出信号，如果队列满则等待
        signals_sent = 0
        for _ in range(thread_count):
            try:
                self.task_queue.put_nowait(None)
                signals_sent += 1
            except queue.Full:
                # 队列已满，尝试等待并重试
                try:
                    self.task_queue.put(None, timeout=1)
                    signals_sent += 1
                except queue.Full:
                    self.logger.warning(
                        f"无法发送退出信号给所有线程，已发送: {signals_sent}/{thread_count}"
                    )
                    break
        
        if signals_sent < thread_count:
            self.logger.warning(
                f"只发送了 {signals_sent}/{thread_count} 个退出信号，"
                f"部分线程可能需要等待超时退出"
            )
        else:
            self.logger.info(f"成功发送 {signals_sent} 个退出信号给工作线程")
    
    def wait_for_threads_exit(self, join_timeout: int) -> None:
        """
        等待所有工作线程退出
        
        在锁内创建线程副本以避免竞态条件，然后逐个等待线程退出。
        如果线程在超时时间内未退出，会记录警告但继续执行。
        
        Args:
            join_timeout: 线程join超时时间（秒）
        """
        # 在锁内创建线程副本，避免竞态条件
        with self.threads_lock:
            threads_to_wait = list(self.worker_threads)
        
        for thread in threads_to_wait:
            if thread.is_alive():
                try:
                    thread.join(timeout=join_timeout)
                    if thread.is_alive():
                        self.logger.warning(f"线程 {thread.name} 在超时后仍未退出")
                    else:
                        self.logger.debug(f"线程 {thread.name} 已退出")
                except RuntimeError as e:
                    # RuntimeError可能发生在join已死线程时
                    self.logger.warning(f"线程 {thread.name} join 失败 [RuntimeError]: {e}")
                except Exception as e:
                    # 其他未预期的异常
                    error_type = type(e).__name__
                    self.logger.warning(
                        f"线程 {thread.name} join 失败 [{error_type}]: {e}"
                    )


class TaskExecutor:
    """
    任务执行器
    
    负责任务的实际执行，包括超时控制和状态更新。
    每个任务在独立的工作线程中执行，支持超时机制。
    
    线程安全说明：
    - execute_task方法可以在多个线程中并发调用
    - 任务执行是独立的，不会相互影响
    - 超时机制使用daemon线程实现，超时后任务线程仍在后台运行
    """
    
    def __init__(
        self,
        logger: logging.Logger,
        task_timeout_getter: Callable[[], Optional[float]],
        update_status_func: Callable[..., None],
    ):
        """
        初始化任务执行器
        
        Args:
            logger: 日志记录器
            task_timeout_getter: 获取任务超时时间的函数（支持动态获取）
            update_status_func: 状态更新函数
        """
        self.logger = logger
        self._get_task_timeout = task_timeout_getter
        self._update_status = update_status_func
    
    def execute_task(self, task: TaskTuple) -> None:
        """
        执行任务
        
        Args:
            task: 任务元组，包含(task_id, func, args, kwargs)
        """
        task_id, func, args, kwargs = task
        start_time = time.time()
        
        try:
            # 更新任务状态为running
            self._update_status(task_id, "running", start_time=start_time)
            self.logger.debug(f"任务 {task_id} 开始执行")
            
            # 执行任务（支持超时）
            result = self._execute_with_timeout(task_id, func, args, kwargs)
            
            # 更新任务状态为completed
            end_time = time.time()
            self._update_status(
                task_id, "completed", start_time=start_time, end_time=end_time, result=result
            )
            self.logger.debug(
                f"任务 {task_id} 执行完成，耗时 {end_time - start_time:.2f}秒"
            )
            
        except KeyboardInterrupt:
            # 键盘中断，标记为失败
            end_time = time.time()
            self._update_status(
                task_id, "failed", start_time=start_time, end_time=end_time, error="任务被中断"
            )
            self.logger.warning(f"任务 {task_id} 被中断")
            raise
        except SystemExit:
            # 系统退出，重新抛出
            raise
        except Exception as e:
            # 记录任务执行异常
            end_time = time.time()
            self._update_status(
                task_id, "failed", start_time=start_time, end_time=end_time, error=str(e)
            )
            error_type = type(e).__name__
            self.logger.error(f"任务 {task_id} 执行失败 [{error_type}]: {e}", exc_info=True)
    
    def _execute_with_timeout(
        self,
        task_id: str,
        func: Callable[..., Any],
        args: tuple,
        kwargs: dict,
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
        # 动态获取最新的超时配置（支持运行时修改）
        task_timeout = self._get_task_timeout()
        if not task_timeout:
            return func(*args, **kwargs)
        
        result_container: Dict[str, Any] = {
            "result": None,
            "exception": None,
            "completed": False,
        }
        
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
        task_thread.join(timeout=task_timeout)
        
        if not result_container["completed"]:
            # 记录超时警告，提醒任务仍在后台运行
            self.logger.warning(
                f"任务 {task_id} 执行超时（{task_timeout}秒），"
                f"但任务线程仍在后台运行，可能导致资源泄漏"
            )
            raise TimeoutError(f"任务 {task_id} 执行超时（{task_timeout}秒）")
        
        if result_container["exception"]:
            raise result_container["exception"]
        
        return result_container["result"]

