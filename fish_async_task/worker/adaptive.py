"""
自适应线程管理模块

包含自适应工作线程管理器和 CPU 监控器。
"""

import logging
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional


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
