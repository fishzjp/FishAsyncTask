"""
工作线程模块

负责工作线程的创建、管理和任务执行。
支持自适应线程管理，根据CPU使用率和队列积压动态调整线程数量。
"""

import logging
import os
import queue
import threading
import time
import uuid
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from .types import TaskStatus, TaskTuple


class AdaptiveWorkerManager:
    """
    自适应工作线程管理器

    基于CPU使用率、队列积压和任务执行时间动态调整线程数量。
    支持CPU监控，在CPU使用率过高时避免过度扩容。

    使用场景：
    - 任务负载波动较大的场景
    - 需要根据系统负载自动调整资源的场景
    - CPU密集型和I/O密集型任务混合的场景

    配置说明：
    - min_workers / max_workers: 线程数边界
    - cpu_threshold: CPU使用率阈值，超过此值时避免扩容
    - queue_threshold_high: 队列积压阈值，达到此值时触发扩容
    - queue_threshold_low: 队列空闲阈值，低于此值时触发缩容
    - scale_up_cooldown: 扩容冷却期（秒），避免频繁扩容
    - scale_down_cooldown: 缩容冷却期（秒），避免频繁缩容
    """

    def __init__(
        self,
        min_workers: int,
        max_workers: int,
        cpu_threshold: float = 0.8,
        queue_threshold_high: int = 100,
        queue_threshold_low: int = 10,
        scale_up_cooldown: float = 5.0,
        scale_down_cooldown: float = 30.0,
        use_cpu_monitoring: bool = True,
    ):
        """
        初始化自适应工作线程管理器

        Args:
            min_workers: 最小工作线程数
            max_workers: 最大工作线程数
            cpu_threshold: CPU使用率阈值（0.0-1.0），超过此值时避免扩容
            queue_threshold_high: 队列积压高阈值，达到此值时触发扩容
            queue_threshold_low: 队列空闲低阈值，低于此值且空闲超时后触发缩容
            scale_up_cooldown: 扩容冷却期（秒）
            scale_down_cooldown: 缩容冷却期（秒）
            use_cpu_monitoring: 是否启用CPU监控
        """
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.cpu_threshold = cpu_threshold
        self.queue_threshold_high = queue_threshold_high
        self.queue_threshold_low = queue_threshold_low
        self.scale_up_cooldown = scale_up_cooldown
        self.scale_down_cooldown = scale_down_cooldown
        self.use_cpu_monitoring = use_cpu_monitoring

        # 冷却期跟踪
        self._last_scale_up = 0.0
        self._last_scale_down = 0.0

        # 任务执行时间统计（最近100个任务）
        self._task_times: Deque[float] = deque(maxlen=100)

        # CPU监控器（可选）
        self._cpu_monitor: Optional["CPUMonitor"] = None
        if use_cpu_monitoring:
            self._cpu_monitor = CPUMonitor()

    def should_scale_up(
        self,
        current_workers: int,
        queue_size: int,
        cpu_usage: Optional[float] = None,
    ) -> bool:
        """
        判断是否应该扩展线程

        扩容条件（需全部满足）：
        1. 当前线程数小于最大限制
        2. 距离上次扩容超过冷却期
        3. 队列积压超过高阈值 或 CPU使用率低于阈值

        Args:
            current_workers: 当前工作线程数
            queue_size: 当前队列积压任务数
            cpu_usage: 当前CPU使用率（0.0-1.0），可选

        Returns:
            bool: 如果应该扩容则返回True
        """
        now = time.time()

        # 条件1: 检查最大线程数限制
        if current_workers >= self.max_workers:
            return False

        # 条件2: 检查扩容冷却期
        if now - self._last_scale_up < self.scale_up_cooldown:
            return False

        # 条件3: 队列积压检查
        if queue_size > self.queue_threshold_high:
            self._last_scale_up = now
            return True

        # 条件4: CPU使用率检查（如果启用）
        if self.use_cpu_monitoring and cpu_usage is not None:
            if cpu_usage < self.cpu_threshold and queue_size > current_workers:
                self._last_scale_up = now
                return True

        return False

    def should_scale_down(
        self,
        current_workers: int,
        queue_size: int,
        idle_time: Optional[float] = None,
    ) -> bool:
        """
        判断是否应该缩减线程

        缩容条件（需全部满足）：
        1. 当前线程数大于最小限制
        2. 距离上次缩容超过冷却期
        3. 队列为空且空闲时间超过阈值

        Args:
            current_workers: 当前工作线程数
            queue_size: 当前队列积压任务数
            idle_time: 队列空闲时间（秒），可选

        Returns:
            bool: 如果应该缩容则返回True
        """
        now = time.time()

        # 条件1: 检查最小线程数限制
        if current_workers <= self.min_workers:
            return False

        # 条件2: 检查缩容冷却期
        if now - self._last_scale_down < self.scale_down_cooldown:
            return False

        # 条件3: 队列为空且空闲时间超过缩容冷却期
        if queue_size == 0 and idle_time is not None:
            # 如果冷却期已禁用（scale_down_cooldown <= 0），不允许缩容
            if self.scale_down_cooldown <= 0:
                return False
            # 如果空闲时间超过缩容冷却期，可以缩容
            if idle_time >= self.scale_down_cooldown:
                self._last_scale_down = now
                return True

        return False

    def record_task_time(self, task_time: float) -> None:
        """
        记录任务执行时间

        Args:
            task_time: 任务执行时间（秒）
        """
        self._task_times.append(task_time)

    def get_avg_task_time(self) -> float:
        """
        获取平均任务执行时间

        Returns:
            float: 平均任务执行时间（秒），如果没有数据则返回0
        """
        if not self._task_times:
            return 0.0
        return sum(self._task_times) / len(self._task_times)

    def get_cpu_usage(self) -> Optional[float]:
        """
        获取当前CPU使用率

        Returns:
            float: CPU使用率（0.0-1.0），如果CPU监控不可用则返回None
        """
        if self._cpu_monitor is not None:
            return self._cpu_monitor.get_cpu_usage()
        return None

    def get_stats(self) -> Dict[str, Any]:
        """
        获取管理器统计信息

        Returns:
            Dict[str, Any]: 统计信息字典
        """
        return {
            "min_workers": self.min_workers,
            "max_workers": self.max_workers,
            "cpu_threshold": self.cpu_threshold,
            "queue_threshold_high": self.queue_threshold_high,
            "queue_threshold_low": self.queue_threshold_low,
            "scale_up_cooldown": self.scale_up_cooldown,
            "scale_down_cooldown": self.scale_down_cooldown,
            "use_cpu_monitoring": self.use_cpu_monitoring,
            "avg_task_time": self.get_avg_task_time(),
            "task_count": len(self._task_times),
            "cpu_usage": self.get_cpu_usage(),
            "last_scale_up": self._last_scale_up,
            "last_scale_down": self._last_scale_down,
        }


class CPUMonitor:
    """
    CPU使用率监控器

    使用psutil获取系统CPU使用率，支持采样平均。
    """

    def __init__(self, sample_interval: float = 0.5, sample_count: int = 3):
        """
        初始化CPU监控器

        Args:
            sample_interval: 每次采样的时间间隔（秒）
            sample_count: 采样次数，用于计算平均CPU使用率
        """
        self.sample_interval = sample_interval
        self.sample_count = sample_count
        self._psutil_available = self._check_psutil()

    def _check_psutil(self) -> bool:
        """
        检查psutil是否可用

        Returns:
            bool: 如果psutil可用则返回True
        """
        try:
            import psutil  # noqa: F401

            return True
        except ImportError:
            return False

    def get_cpu_usage(self) -> Optional[float]:
        """
        获取CPU使用率

        如果psutil不可用，返回None。

        Returns:
            float: CPU使用率（0.0-1.0），如果不可用则返回None
        """
        if not self._psutil_available:
            return None

        try:
            import psutil

            # 采样多次计算平均CPU使用率
            cpu_percentages: List[float] = []
            for _ in range(self.sample_count):
                cpu_percent = psutil.cpu_percent(interval=self.sample_interval)
                cpu_percentages.append(float(cpu_percent))

            # 返回平均CPU使用率
            avg_cpu = sum(cpu_percentages) / len(cpu_percentages)
            return avg_cpu / 100.0  # 转换为0.0-1.0范围
        except Exception:
            # 如果获取失败，返回None
            return None

    def get_cpu_count(self) -> int:
        """
        获取CPU核心数

        如果psutil不可用或返回None，返回1。

        Returns:
            int: CPU核心数
        """
        if not self._psutil_available:
            return 1

        try:
            import psutil

            count = psutil.cpu_count()
            return count if count is not None else 1
        except Exception:
            return 1


class WorkerManager:
    """
    工作线程管理器

    负责管理工作线程的生命周期，包括创建、扩展和回收。
    支持动态线程池，根据任务队列大小和CPU使用率自动调整线程数量。
    使用自适应策略，在负载高时扩容，空闲时缩容。

    线程安全说明：
    - 所有对worker_threads列表的操作都在threads_lock保护下进行
    - 线程退出时会从列表中安全移除，避免竞态条件
    - 自适应扩缩容操作在threads_lock保护下进行
    """

    # 配置常量
    QUEUE_GET_TIMEOUT = 1  # 队列获取超时时间（秒）
    QUEUE_PUT_TIMEOUT = 1  # 队列放入超时时间（秒）

    # 默认自适应配置
    DEFAULT_CPU_THRESHOLD = 0.8  # 默认CPU阈值
    DEFAULT_QUEUE_THRESHOLD_HIGH = 100  # 默认扩容队列阈值
    DEFAULT_QUEUE_THRESHOLD_LOW = 10  # 默认缩容队列阈值
    DEFAULT_SCALE_UP_COOLDOWN = 5.0  # 默认扩容冷却期
    DEFAULT_SCALE_DOWN_COOLDOWN = 30.0  # 默认缩容冷却期

    # 实例属性类型声明
    _adaptive_manager: Optional["AdaptiveWorkerManager"]

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
        adaptive_worker_enabled: bool = True,
        cpu_threshold: Optional[float] = None,
        queue_threshold_high: Optional[int] = None,
        queue_threshold_low: Optional[int] = None,
        scale_up_cooldown: Optional[float] = None,
        scale_down_cooldown: Optional[float] = None,
        use_cpu_monitoring: bool = True,
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
            adaptive_worker_enabled: 是否启用自适应扩缩容
            cpu_threshold: CPU使用率阈值（可选）
            queue_threshold_high: 扩容队列积压阈值（可选）
            queue_threshold_low: 缩容队列空闲阈值（可选）
            scale_up_cooldown: 扩容冷却期（秒）（可选）
            scale_down_cooldown: 缩容冷却期（秒）（可选）
            use_cpu_monitoring: 是否启用CPU监控
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
        self.adaptive_worker_enabled = adaptive_worker_enabled

        # 从环境变量读取配置（如果未提供）
        self.cpu_threshold = self._load_config_float(
            "WORKER_CPU_THRESHOLD", cpu_threshold, self.DEFAULT_CPU_THRESHOLD
        )
        self.queue_threshold_high = self._load_config_int(
            "WORKER_QUEUE_THRESHOLD_HIGH", queue_threshold_high, self.DEFAULT_QUEUE_THRESHOLD_HIGH
        )
        self.queue_threshold_low = self._load_config_int(
            "WORKER_QUEUE_THRESHOLD_LOW", queue_threshold_low, self.DEFAULT_QUEUE_THRESHOLD_LOW
        )
        self.scale_up_cooldown = self._load_config_float(
            "WORKER_SCALE_UP_COOLDOWN", scale_up_cooldown, self.DEFAULT_SCALE_UP_COOLDOWN
        )
        self.scale_down_cooldown = self._load_config_float(
            "WORKER_SCALE_DOWN_COOLDOWN", scale_down_cooldown, self.DEFAULT_SCALE_DOWN_COOLDOWN
        )

        # 初始化自适应工作线程管理器
        if adaptive_worker_enabled:
            self._adaptive_manager = AdaptiveWorkerManager(
                min_workers=min_workers,
                max_workers=max_workers,
                cpu_threshold=self.cpu_threshold,
                queue_threshold_high=self.queue_threshold_high,
                queue_threshold_low=self.queue_threshold_low,
                scale_up_cooldown=self.scale_up_cooldown,
                scale_down_cooldown=self.scale_down_cooldown,
                use_cpu_monitoring=use_cpu_monitoring,
            )
        else:
            self._adaptive_manager = None

        # 空闲时间跟踪
        self._idle_start_time: Optional[float] = None

    def _load_config_float(self, env_key: str, value: Optional[float], default: float) -> float:
        """加载浮点配置"""
        if value is not None:
            return value
        env_value = os.getenv(env_key)
        if env_value:
            try:
                return float(env_value)
            except ValueError:
                self.logger.warning(f"无效的 {env_key}: {env_value}，使用默认值 {default}")
        return default

    def _load_config_int(self, env_key: str, value: Optional[int], default: int) -> int:
        """加载整数配置"""
        if value is not None:
            return value
        env_value = os.getenv(env_key)
        if env_value:
            try:
                return int(env_value)
            except ValueError:
                self.logger.warning(f"无效的 {env_key}: {env_value}，使用默认值 {default}")
        return default

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
        根据队列大小和CPU使用率动态扩展工作线程

        当队列中的任务数量超过当前线程数时，自动创建新线程。
        线程数量不会超过 max_workers 限制。
        使用自适应策略，考虑CPU使用率和队列积压情况。
        """
        with self.threads_lock:
            current_thread_count = len(self.worker_threads)
            queue_size = self.task_queue.qsize()

            if current_thread_count >= self.max_workers:
                return

            if self._adaptive_manager is not None:
                # 使用自适应策略判断
                cpu_usage = self._adaptive_manager.get_cpu_usage()
                if self._adaptive_manager.should_scale_up(
                    current_thread_count, queue_size, cpu_usage
                ):
                    self._create_and_start_worker()
            else:
                # 原始策略：队列积压超过当前线程数时扩容
                if queue_size > current_thread_count:
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
        self.logger.info("启动新工作线程，当前线程数: %d", len(self.worker_threads))

    def record_task_time(self, task_time: float) -> None:
        """
        记录任务执行时间（用于自适应管理）

        Args:
            task_time: 任务执行时间（秒）
        """
        if self._adaptive_manager is not None:
            self._adaptive_manager.record_task_time(task_time)

    def get_idle_time(self) -> Optional[float]:
        """
        获取当前队列空闲时间

        Returns:
            float: 队列空闲时间（秒），如果当前不空闲则返回None
        """
        if self._idle_start_time is None:
            return None
        return time.time() - self._idle_start_time

    def should_scale_down(self) -> bool:
        """
        判断是否应该缩减线程（使用自适应策略）

        Returns:
            bool: 如果应该缩容则返回True
        """
        if self._adaptive_manager is None:
            return False

        with self.threads_lock:
            current_workers = len(self.worker_threads)
            queue_size = self.task_queue.qsize()
            idle_time = self.get_idle_time()

            return self._adaptive_manager.should_scale_down(current_workers, queue_size, idle_time)

    def get_adaptive_stats(self) -> Optional[Dict[str, Any]]:
        """
        获取自适应管理器的统计信息

        Returns:
            Dict[str, Any]: 统计信息字典，如果自适应管理未启用则返回None
        """
        if self._adaptive_manager is not None:
            return self._adaptive_manager.get_stats()
        return None

    def _check_idle_timeout(self, thread_name: str, idle_start: Optional[float]) -> bool:
        """
        检查空闲超时，如果超时则尝试退出线程

        Args:
            thread_name: 线程名称
            idle_start: 空闲开始时间

        Returns:
            bool: 如果应该退出线程则返回True，否则返回False
        """
        now = time.time()
        if idle_start is None:
            return False

        idle_duration = now - idle_start

        # 使用自适应策略判断是否应该缩容
        if self._adaptive_manager is not None:
            with self.threads_lock:
                current_workers = len(self.worker_threads)
                queue_size = self.task_queue.qsize()

                if self._adaptive_manager.should_scale_down(
                    current_workers, queue_size, idle_duration
                ):
                    # 执行缩容
                    current_thread = threading.current_thread()
                    if len(self.worker_threads) > self.min_workers:
                        if current_thread in self.worker_threads:
                            self.worker_threads.remove(current_thread)
                            self.logger.info(f"空闲线程退出（自适应）: {thread_name}")
                            return True
                    else:
                        self.logger.debug(f"线程 {thread_name} 已达到最小线程数限制，不退出")
                        return True
            return False

        # 原始策略：使用 idle_timeout
        if idle_duration >= self.idle_timeout:
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
                        return True
                    # 如果线程不在列表中，说明已被其他操作移除，直接退出
                    else:
                        self.logger.debug(f"线程 {thread_name} 已被移除，退出")
                        return True
        return False

    def _worker_loop(self) -> None:
        """
        工作线程主循环

        从任务队列中获取任务并执行。当空闲时间超过 idle_timeout 且
        当前线程数大于 min_workers 时，线程会自动退出以节省资源。
        同时记录任务执行时间用于自适应管理。
        """
        thread_name = threading.current_thread().name
        self.logger.debug("工作线程启动: %s", thread_name)
        idle_start: Optional[float] = None

        while self._running_event.is_set():
            try:
                task = self.task_queue.get(timeout=self.QUEUE_GET_TIMEOUT)

                # 退出信号
                if task is None:
                    self.task_queue.task_done()
                    break

                idle_start = None
                task_start_time = time.time()

                # 执行任务
                self._execute_task(task)
                self.task_queue.task_done()

                # 记录任务执行时间（用于自适应管理）
                task_end_time = time.time()
                self.record_task_time(task_end_time - task_start_time)

            except queue.Empty:
                now = time.time()
                if idle_start is None:
                    idle_start = now
                    # 更新空闲开始时间（用于自适应管理）
                    if self._adaptive_manager is not None:
                        self._idle_start_time = idle_start
                elif self._check_idle_timeout(thread_name, idle_start):
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
            except TimeoutError as e:
                # 超时异常，记录警告但继续运行
                self.logger.warning(f"工作线程任务执行超时: {e}")
            except (IOError, OSError, ConnectionError) as e:
                # I/O 相关异常，可能是临时性问题，记录警告并继续
                self.logger.warning(f"工作线程遇到 I/O 相关异常 [{type(e).__name__}]: {e}")
            except (MemoryError, ResourceWarning) as e:
                # 资源相关异常，记录错误但尝试继续运行
                self.logger.error(f"工作线程遇到资源异常 [{type(e).__name__}]: {e}", exc_info=True)
            except (TimeoutError, RuntimeError) as e:
                # 超时和运行时错误，记录错误但继续运行
                self.logger.error(
                    f"工作线程遇到运行时异常 [{type(e).__name__}]: {e}", exc_info=True
                )
            except Exception as e:
                # 记录未预期的异常，但不中断线程运行
                # 这确保了单个任务的异常不会影响整个线程池的运行
                error_type = type(e).__name__
                # 注意：这里捕获所有异常是为了保持线程池运行
                # 如果是编程错误（TypeError、AttributeError等），应该修复而不是掩盖
                if error_type in (
                    "TypeError",
                    "AttributeError",
                    "ValueError",
                    "KeyError",
                    "IndexError",
                ):
                    # 编程错误应该向上传播，以便开发时发现
                    self.logger.critical(
                        f"工作线程遇到编程错误 [{error_type}]: {e}，建议修复代码", exc_info=True
                    )
                    # 重新抛出编程错误，以便快速失败
                    raise
                else:
                    self.logger.error(f"工作线程执行未预期异常 [{error_type}]: {e}", exc_info=True)

        self.logger.debug("工作线程退出: %s", thread_name)

    def send_shutdown_signals(self) -> None:
        """
        向所有工作线程发送退出信号

        通过向任务队列中放入 None 值来通知工作线程退出。
        如果队列已满，会尝试等待并重试。
        """
        with self.threads_lock:
            thread_count = len(self.worker_threads)

        # 尝试发送退出信号,如果队列满则等待
        signals_sent = 0
        for _ in range(thread_count):
            try:
                # type: ignore[arg-type]  # None是特殊的退出信号
                self.task_queue.put_nowait(None)  # type: ignore[arg-type]
                signals_sent += 1
            except queue.Full:
                # 队列已满,尝试等待并重试
                try:
                    # type: ignore[arg-type]  # None是特殊的退出信号
                    self.task_queue.put(None, timeout=self.QUEUE_PUT_TIMEOUT)  # type: ignore[arg-type]
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
                    self.logger.warning(f"线程 {thread.name} join 失败 [{error_type}]: {e}")


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
            current_time = time.time()
            self.logger.warning(
                f"任务 {task_id} 执行超时（{task_timeout}秒），"
                f"但任务线程仍在后台运行，可能导致资源泄漏"
            )

            # 跟踪超时任务（用于后续清理和监控）
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

            # 调用清理回调
            self._trigger_cleanup_callbacks(task_id)

            raise TimeoutError(f"任务 {task_id} 执行超时（{task_timeout}秒）")

        if result_container["exception"]:
            raise result_container["exception"]

        return result_container["result"]

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
