"""
异步任务管理器

纯Python实现的异步任务管理器，支持线程池和动态伸缩。
适用于需要异步执行任务的场景，如后台任务处理、批量数据处理等。
"""

import os
import threading
import queue
import uuid
import time
import logging
from typing import Any, Callable, Dict, List, Optional

from .types import TaskTuple, TaskStatusDict
from .config import ConfigLoader
from .task_status import TaskStatusManager
from .worker import WorkerManager, TaskExecutor
from .cleanup import CleanupThreadManager


class TaskQueueFullError(Exception):
    """任务队列已满异常"""
    pass


class TaskManager:
    """纯Python实现的异步任务管理器（线程池 + 动态伸缩）"""
    
    # 默认配置常量
    DEFAULT_QUEUE_SIZE = 1000
    DEFAULT_MIN_WORKERS = 1
    DEFAULT_IDLE_TIMEOUT = 60  # 秒
    DEFAULT_TASK_STATUS_TTL = 3600  # 1小时
    DEFAULT_MAX_TASK_STATUS_COUNT = 10000
    DEFAULT_CLEANUP_INTERVAL = 300  # 5分钟
    DEFAULT_THREAD_JOIN_TIMEOUT = 2  # 秒
    DEFAULT_TASK_TIMEOUT = None  # 默认无超时限制

    _instance_lock = threading.Lock()
    _instances: Dict[str, "TaskManager"] = {}

    def __new__(cls, instance_key: str = "default") -> "TaskManager":
        """
        单例模式实现
        
        使用双重检查锁定模式确保线程安全。
        支持通过 instance_key 创建多个不同的单例实例。
        
        使用场景：
        - 默认情况下，使用 "default" 作为 instance_key，所有调用返回同一个实例
        - 如果需要多个独立的任务管理器实例（例如：不同业务模块使用不同的管理器），
          可以使用不同的 instance_key，每个 key 对应一个独立的单例实例
        
        示例：
            # 获取默认实例
            manager1 = TaskManager()
            manager2 = TaskManager()  # manager1 和 manager2 是同一个实例
            
            # 获取不同业务模块的独立实例
            order_manager = TaskManager(instance_key="order")
            payment_manager = TaskManager(instance_key="payment")  # 独立的实例
        
        Args:
            instance_key: 实例键名，默认为 "default"。不同的 key 对应不同的单例实例。
            
        Returns:
            TaskManager: 任务管理器实例（单例）
        """
        if instance_key not in cls._instances:
            with cls._instance_lock:
                # 双重检查，避免多个线程同时创建实例
                if instance_key not in cls._instances:
                    # 先创建实例对象
                    instance = super().__new__(cls)
                    # 存储 instance_key，用于后续验证
                    instance._instance_key = instance_key
                    # 确保实例已创建后再初始化
                    # 注意：此时实例属性尚未初始化，_init_task_manager会初始化所有属性
                    instance._init_task_manager()
                    cls._instances[instance_key] = instance
        return cls._instances[instance_key]
    
    def __init__(self, instance_key: str = "default") -> None:
        """
        初始化方法（单例模式下此方法不会重复执行）
        
        注意：由于使用单例模式，实际的初始化在 __new__ 中通过
        _init_task_manager 完成。此方法存在是为了符合Python对象
        创建规范，主要用于验证 instance_key 的一致性。
        
        单例模式实现说明：
        - Python 的对象创建流程：__new__ -> __init__
        - 在单例模式中，__new__ 负责创建或返回已有实例
        - 如果实例已存在，Python 仍会调用 __init__，但此时实例已经初始化完成
        - 此方法会验证 instance_key 是否匹配，避免混淆
        
        Args:
            instance_key: 实例键名，应该与创建实例时使用的 key 一致
        """
        # 验证 instance_key 是否匹配（仅在实例已存在时）
        if hasattr(self, "_instance_key") and self._instance_key != instance_key:
            # 安全访问 logger（可能在单例模式下尚未初始化）
            logger = getattr(self, "logger", logging.getLogger(__name__))
            logger.warning(
                f"警告：尝试使用 instance_key='{instance_key}' 访问实例，"
                f"但该实例的实际 instance_key 为 '{self._instance_key}'。"
                f"这可能是编程错误，建议检查代码。"
            )

    def _init_task_manager(self) -> None:
        """初始化任务管理器"""
        # 初始化logger（需要在验证 instance_key 之前初始化）
        self.logger = logging.getLogger(__name__)
        
        # 初始化基础数据结构
        self.task_queue: "queue.Queue[TaskTuple]" = (
            queue.Queue(maxsize=self.DEFAULT_QUEUE_SIZE)
        )
        self.task_status: Dict[str, TaskStatusDict] = {}
        self.worker_threads: List[threading.Thread] = []
        self.status_lock = threading.Lock()
        self.threads_lock = threading.Lock()

        # 初始化logger
        self.logger = logging.getLogger(__name__)

        # 初始化配置加载器
        config_loader = ConfigLoader(self.logger)
        
        # 初始化工作线程配置
        self.min_workers = self.DEFAULT_MIN_WORKERS
        cpu_count = os.cpu_count() or 1
        self.max_workers = max(4, cpu_count * 4)
        self.idle_timeout = self.DEFAULT_IDLE_TIMEOUT
        
        # 加载并验证配置
        self.task_status_ttl = config_loader.load_int_config(
            "TASK_STATUS_TTL", self.DEFAULT_TASK_STATUS_TTL, "TASK_STATUS_TTL"
        )
        self.max_task_status_count = config_loader.load_int_config(
            "MAX_TASK_STATUS_COUNT",
            self.DEFAULT_MAX_TASK_STATUS_COUNT,
            "MAX_TASK_STATUS_COUNT",
        )
        self.cleanup_interval = config_loader.load_int_config(
            "TASK_CLEANUP_INTERVAL",
            self.DEFAULT_CLEANUP_INTERVAL,
            "TASK_CLEANUP_INTERVAL",
        )
        self.task_timeout = config_loader.load_timeout_config(self.DEFAULT_TASK_TIMEOUT)

        # 初始化运行标志
        self._running_event = threading.Event()
        self._running_event.set()
        
        # 初始化任务状态管理器
        self.status_manager = TaskStatusManager(
            self.logger,
            self.status_lock,
            self.task_status,
            self.task_status_ttl,
            self.max_task_status_count,
        )
        
        # 初始化任务执行器（使用lambda动态获取超时值）
        self.task_executor = TaskExecutor(
            self.logger,
            lambda: self.task_timeout,
            self.status_manager.update_task_status,
        )
        
        # 初始化工作线程管理器
        self.worker_manager = WorkerManager(
            self.logger,
            self.task_queue,
            self.worker_threads,
            self.threads_lock,
            self._running_event,
            self.min_workers,
            self.max_workers,
            self.idle_timeout,
            self.task_timeout,
            self.task_executor.execute_task,
        )
        
        # 初始化清理线程管理器
        self.cleanup_manager = CleanupThreadManager(
            self.logger,
            self._running_event,
            self.cleanup_interval,
            self.status_manager.cleanup_old_task_status,
        )
        
        self.logger.info(
            f"任务管理器初始化完成 - TTL: {self.task_status_ttl}s, "
            f"最大状态数: {self.max_task_status_count}, "
            f"清理间隔: {self.cleanup_interval}s, "
            f"任务超时: {self.task_timeout or '无限制'}s"
        )

        # 启动初始线程和清理线程
        self.worker_manager.start_initial_workers()
        self.cleanup_manager.start()

    def submit_task(
        self, 
        func: Callable[..., Any], 
        *args: Any, 
        block: bool = False,
        timeout: Optional[float] = None,
        **kwargs: Any
    ) -> str:
        """
        提交任务到任务队列
        
        此方法是线程安全的，可以在多个线程中并发调用。
        任务会被添加到队列中，由工作线程异步执行。
        
        Args:
            func: 要执行的任务函数
            *args: 任务函数的 positional 参数
            block: 如果队列已满，是否阻塞等待。默认为 False。
            timeout: 阻塞等待的超时时间（秒）。仅在 block=True 时有效。
                     如果为 None，则无限等待。默认为 None。
            **kwargs: 任务函数的关键字参数
            
        Returns:
            str: 任务ID
            
        Raises:
            TaskQueueFullError: 当队列已满且 block=False 时抛出
            
        Note:
            - 任务函数应该是线程安全的
            - 如果 block=False 且队列已满，会抛出 TaskQueueFullError 异常
            - 如果 block=True，会阻塞等待直到队列有空间或超时
            - 提交后任务状态为"pending"，执行时变为"running"，完成后变为"completed"或"failed"
        """
        task_id = str(uuid.uuid4())

        try:
            if block:
                self.task_queue.put((task_id, func, args, kwargs), timeout=timeout)
            else:
                self.task_queue.put_nowait((task_id, func, args, kwargs))
        except queue.Full:
            error_msg = f"任务队列已满，无法提交任务 {task_id}"
            self.logger.error(error_msg)
            raise TaskQueueFullError(error_msg)

        # 更新任务状态为pending
        self.status_manager.update_task_status(task_id, "pending", submit_time=time.time())

        self.worker_manager.scale_up_workers_if_needed()
        self.logger.debug(f"已提交任务 {task_id} 到队列")
        return task_id

    def get_task_status(self, task_id: str) -> Optional[TaskStatusDict]:
        """
        获取任务状态
        
        此方法是线程安全的，可以在多个线程中并发调用。
        
        Args:
            task_id: 任务ID
            
        Returns:
            Optional[TaskStatusDict]: 任务状态字典，包含以下字段：
                - status: 任务状态（"pending"、"running"、"completed"、"failed"）
                - submit_time: 提交时间（时间戳，可选）
                - start_time: 开始执行时间（时间戳，可选）
                - end_time: 结束时间（时间戳，可选）
                - result: 任务执行结果（仅当status为"completed"时存在）
                - error: 错误信息（仅当status为"failed"时存在）
            如果任务不存在或已被清理，则返回None
        """
        return self.status_manager.get_task_status(task_id)

    def clear_task_status(self, task_id: Optional[str] = None) -> None:
        """
        清除指定任务状态或所有任务状态
        
        此方法是线程安全的，可以在多个线程中并发调用。
        
        Args:
            task_id: 要清除的任务ID。如果为None，则清除所有任务状态。
            
        Note:
            - 清除任务状态不会影响正在执行的任务
            - 清除后，get_task_status将返回None
        """
        self.status_manager.clear_task_status(task_id)

    def shutdown(self) -> None:
        """
        关闭任务管理器
        
        优雅关闭流程：
        1. 清除运行标志，停止接受新任务
        2. 发送退出信号给所有工作线程
        3. 等待所有工作线程退出
        4. 等待清理线程退出
        5. 清理所有资源（线程列表、任务状态等）
        
        注意：如果多次调用，只有第一次调用会生效。
        """
        if not self._running_event.is_set():
            self.logger.info("任务管理器已经关闭，跳过重复关闭")
            return

        self._running_event.clear()
        self.logger.info("正在关闭任务管理器...")

        # 发送退出信号给所有工作线程
        self.worker_manager.send_shutdown_signals()

        # 等待所有工作线程退出
        self.worker_manager.wait_for_threads_exit(self.DEFAULT_THREAD_JOIN_TIMEOUT)
        
        # 等待清理线程退出
        self.cleanup_manager.join(self.DEFAULT_THREAD_JOIN_TIMEOUT)

        # 清理资源（在所有线程退出后再清理）
        with self.threads_lock:
            self.worker_threads.clear()
        with self.status_lock:
            self.task_status.clear()
        self.logger.info("任务管理器已关闭")
