"""自适应工作线程管理

实现自适应线程管理，根据 CPU 使用率和队列大小智能调整工作线程数量。
支持 psutil 可选依赖，优雅降级到基于队列的决策。
"""

import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

from fish_async_task.performance._logging import get_logger


class AdaptiveWorkerManager:
    """
    自适应工作线程管理器

    根据系统 CPU 使用率、任务队列大小和任务执行时间，
    智能调整工作线程数量以优化性能和资源利用率。

    Attributes:
        min_workers: 最小工作线程数
        max_workers: 最大工作线程数
        scale_up_cooldown: 扩展冷却期（秒）
        scale_down_cooldown: 缩减冷却期（秒）
        cpu_threshold: CPU 使用率阈值（0-1）
        queue_threshold: 队列大小阈值

    Examples:
        >>> manager = AdaptiveWorkerManager(
        ...     min_workers=2,
        ...     max_workers=10,
        ...     cpu_threshold=0.8
        ... )
        >>> should_scale, reason = manager.should_scale_up(
        ...     current_workers=5,
        ...     queue_size=100
        ... )
        >>> if should_scale:
        ...     # 增加工作线程
        ...     pass
    """

    def __init__(
        self,
        min_workers: int = 2,
        max_workers: int = 10,
        scale_up_cooldown: float = 30.0,
        scale_down_cooldown: float = 60.0,
        cpu_threshold: float = 0.8,
        queue_threshold: int = 100,
    ) -> None:
        """
        初始化自适应工作线程管理器

        Args:
            min_workers: 最小工作线程数，默认 2
            max_workers: 最大工作线程数，默认 10
            scale_up_cooldown: 扩展冷却期（秒），默认 30.0
            scale_down_cooldown: 缩减冷却期（秒），默认 60.0
            cpu_threshold: CPU 使用率阈值（0-1），默认 0.8
            queue_threshold: 队列大小阈值，默认 100

        Raises:
            ValueError: 如果参数无效
        """
        if min_workers < 1:
            raise ValueError(f"min_workers 必须 >= 1，当前值: {min_workers}")
        if max_workers < min_workers:
            raise ValueError(
                f"max_workers 必须 >= min_workers，当前值: max={max_workers}, min={min_workers}"
            )
        if scale_up_cooldown <= 0:
            raise ValueError(f"scale_up_cooldown 必须 > 0，当前值: {scale_up_cooldown}")
        if scale_down_cooldown <= 0:
            raise ValueError(f"scale_down_cooldown 必须 > 0，当前值: {scale_down_cooldown}")
        if not (0.0 < cpu_threshold <= 1.0):
            raise ValueError(f"cpu_threshold 必须 在 (0, 1] 范围内，当前值: {cpu_threshold}")
        if queue_threshold < 1:
            raise ValueError(f"queue_threshold 必须 >= 1，当前值: {queue_threshold}")

        self.min_workers = min_workers
        self.max_workers = max_workers
        self.scale_up_cooldown = scale_up_cooldown
        self.scale_down_cooldown = scale_down_cooldown
        self.cpu_threshold = cpu_threshold
        self.queue_threshold = queue_threshold

        # 任务执行时间跟踪
        self._task_times: deque[float] = deque(maxlen=1000)
        self._task_times_lock = threading.Lock()

        # 扩展/缩减时间戳
        self._last_scale_up_time: float = 0.0
        self._last_scale_down_time: float = 0.0
        self._scale_time_lock = threading.Lock()

        # 日志记录器
        self.logger = get_logger()

        self.logger.info(
            f"初始化自适应工作线程管理器：min={min_workers}, max={max_workers}, "
            f"cpu_threshold={cpu_threshold}, queue_threshold={queue_threshold}"
        )

    def should_scale_up(
        self, current_workers: int, queue_size: int, cpu_usage: Optional[float] = None
    ) -> tuple[bool, str]:
        """
        判断是否应该扩展工作线程

        Args:
            current_workers: 当前工作线程数
            queue_size: 当前队列大小
            cpu_usage: 当前 CPU 使用率（0-1），如果为 None 则自动获取

        Returns:
            (should_scale, reason) 元组
            - should_scale: 是否应该扩展
            - reason: 扩展原因的描述

        Thread-Safety:
            线程安全

        Examples:
            >>> manager = AdaptiveWorkerManager()
            >>> should_scale, reason = manager.should_scale_up(
            ...     current_workers=5,
            ...     queue_size=100
            ... )
        """
        # 检查是否已达到最大工作线程数
        if current_workers >= self.max_workers:
            return False, f"已达到最大工作线程数 ({self.max_workers})"

        # 检查扩展冷却期
        with self._scale_time_lock:
            current_time = time.time()
            time_since_last_scale = current_time - self._last_scale_up_time

            if time_since_last_scale < self.scale_up_cooldown:
                remaining_time = self.scale_up_cooldown - time_since_last_scale
                return False, f"扩展冷却期中，剩余 {remaining_time:.1f} 秒"

        # 获取 CPU 使用率
        if cpu_usage is None:
            cpu_usage = self.get_cpu_usage()

        # 如果 CPU 使用率过高，不应该扩展
        if cpu_usage is not None and cpu_usage > self.cpu_threshold:
            return False, f"CPU 使用率过高 ({cpu_usage:.1%} > {self.cpu_threshold:.1%})"

        # 如果队列大小超过阈值，应该扩展
        if queue_size > self.queue_threshold:
            with self._scale_time_lock:
                self._last_scale_up_time = time.time()

            cpu_str = f"{cpu_usage:.1%}" if cpu_usage is not None else "N/A"
            self.logger.info(
                f"决定扩展工作线程：当前={current_workers}, "
                f"队列大小={queue_size}, CPU={cpu_str}"
            )
            return True, f"队列大小 ({queue_size}) 超过阈值 ({self.queue_threshold})"

        return False, f"队列大小 ({queue_size}) 未达到扩展阈值 ({self.queue_threshold})"

    def should_scale_down(self, current_workers: int, queue_size: int) -> tuple[bool, str]:
        """
        判断是否应该缩减工作线程

        Args:
            current_workers: 当前工作线程数
            queue_size: 当前队列大小

        Returns:
            (should_scale, reason) 元组
            - should_scale: 是否应该缩减
            - reason: 缩减原因的描述

        Thread-Safety:
            线程安全

        Examples:
            >>> manager = AdaptiveWorkerManager()
            >>> should_scale, reason = manager.should_scale_down(
            ...     current_workers=8,
            ...     queue_size=5
            ... )
        """
        # 检查是否已达到最小工作线程数
        if current_workers <= self.min_workers:
            return False, f"已达到最小工作线程数 ({self.min_workers})"

        # 检查缩减冷却期
        with self._scale_time_lock:
            current_time = time.time()
            time_since_last_scale = current_time - self._last_scale_down_time

            if time_since_last_scale < self.scale_down_cooldown:
                remaining_time = self.scale_down_cooldown - time_since_last_scale
                return False, f"缩减冷却期中，剩余 {remaining_time:.1f} 秒"

        # 获取平均任务执行时间
        avg_task_time = self.get_avg_task_time()

        # 如果队列很小且任务执行很快，应该缩减
        if queue_size < self.queue_threshold / 2:  # 队列小于阈值的一半
            if avg_task_time > 0 and avg_task_time < 0.1:  # 任务执行时间 < 100ms
                with self._scale_time_lock:
                    self._last_scale_down_time = time.time()

                self.logger.info(
                    f"决定缩减工作线程：当前={current_workers}, "
                    f"队列大小={queue_size}, 平均任务时间={avg_task_time:.3f}s"
                )
                return (
                    True,
                    f"队列小 ({queue_size}) 且任务执行快 ({avg_task_time:.3f}s)",
                )

        return False, f"队列大小 ({queue_size}) 或任务执行时间未达到缩减条件"

    def record_task_time(self, execution_time: float) -> None:
        """
        记录任务执行时间

        Args:
            execution_time: 任务执行时间（秒）

        Thread-Safety:
            线程安全

        Examples:
            >>> manager = AdaptiveWorkerManager()
            >>> manager.record_task_time(0.5)  # 记录 500ms 的任务
        """
        if execution_time < 0:
            raise ValueError(f"execution_time 必须 >= 0，当前值: {execution_time}")

        with self._task_times_lock:
            self._task_times.append(execution_time)

    def get_avg_task_time(self) -> float:
        """
        获取平均任务执行时间

        Returns:
            平均任务执行时间（秒），如果没有记录则返回 0.0

        Thread-Safety:
            线程安全（返回近似值，但非常准确）

        Examples:
            >>> manager = AdaptiveWorkerManager()
            >>> manager.record_task_time(0.1)
            >>> manager.record_task_time(0.2)
            >>> manager.get_avg_task_time()
            0.15
        """
        with self._task_times_lock:
            if not self._task_times:
                return 0.0
            return sum(self._task_times) / len(self._task_times)

    def get_cpu_usage(self) -> Optional[float]:
        """
        获取当前 CPU 使用率

        Returns:
            CPU 使用率（0-1），如果 psutil 不可用则返回 None

        Note:
            需要 psutil 可选依赖。如果不可用，返回 None。

        Examples:
            >>> manager = AdaptiveWorkerManager()
            >>> cpu = manager.get_cpu_usage()
            >>> if cpu is not None:
            ...     print(f"CPU 使用率: {cpu:.1%}")
        """
        try:
            import psutil

            # 返回 CPU 使用率（0-1）
            return float(psutil.cpu_percent(interval=0.1) / 100.0)
        except ImportError:
            # psutil 不可用，优雅降级
            return None
        except Exception as e:
            # 获取 CPU 使用率时出错，记录日志并返回 None
            self.logger.warning(f"获取 CPU 使用率失败: {e}")
            return None

    def get_scaling_metrics(self, current_workers: int = 0, queue_size: int = 0) -> Dict[str, Any]:
        """
        获取扩展指标

        Args:
            current_workers: 当前工作线程数
            queue_size: 当前队列大小

        Returns:
            包含扩展指标的字典，包括：
            - current_workers: 当前工作线程数
            - avg_task_time: 平均任务执行时间
            - cpu_usage: CPU 使用率
            - last_scale_up_time: 最后一次扩展时间
            - last_scale_down_time: 最后一次缩减时间
            - queue_size: 队列大小

        Thread-Safety:
            线程安全

        Examples:
            >>> manager = AdaptiveWorkerManager()
            >>> metrics = manager.get_scaling_metrics(
            ...     current_workers=5,
            ...     queue_size=10
            ... )
            >>> print(f"平均任务时间: {metrics['avg_task_time']:.3f}s")
        """
        with self._scale_time_lock:
            last_scale_up = self._last_scale_up_time
            last_scale_down = self._last_scale_down_time

        return {
            "current_workers": current_workers,
            "avg_task_time": self.get_avg_task_time(),
            "cpu_usage": self.get_cpu_usage(),
            "last_scale_up_time": last_scale_up,
            "last_scale_down_time": last_scale_down,
            "queue_size": queue_size,
        }
