"""
性能监控模块

提供运行时性能指标收集和系统健康状态监控功能。
"""

import logging
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional


class PerformanceMetrics:
    """性能指标收集器"""

    def __init__(self, max_history: int = 1000):
        """
        初始化性能指标收集器

        Args:
            max_history: 最大历史记录数
        """
        self._max_history = max_history
        self._lock = threading.Lock()

        self._tasks_submitted: int = 0
        self._tasks_completed: int = 0
        self._tasks_failed: int = 0
        self._tasks_cancelled: int = 0
        self._total_execution_time: float = 0.0
        self._total_queue_wait_time: float = 0.0
        self._total_cleanup_time: float = 0.0
        self._cleanup_count: int = 0

        self._execution_times: deque = deque(maxlen=max_history)
        self._queue_wait_times: deque = deque(maxlen=max_history)
        self._cleanup_times: deque = deque(maxlen=max_history)

        self._start_time = time.time()

    def record_task_submitted(self) -> None:
        """记录任务提交"""
        with self._lock:
            self._tasks_submitted += 1

    def record_task_completed(self, execution_time: float, queue_wait_time: float = 0.0) -> None:
        """
        记录任务完成

        Args:
            execution_time: 任务执行时间（秒）
            queue_wait_time: 任务在队列中等待时间（秒）
        """
        with self._lock:
            self._tasks_completed += 1
            self._total_execution_time += execution_time
            self._total_queue_wait_time += queue_wait_time
            self._execution_times.append(execution_time)
            self._queue_wait_times.append(queue_wait_time)

    def record_task_failed(self, execution_time: float, queue_wait_time: float = 0.0) -> None:
        """
        记录任务失败

        Args:
            execution_time: 任务执行时间（秒）
            queue_wait_time: 任务在队列中等待时间（秒）
        """
        with self._lock:
            self._tasks_failed += 1
            self._total_execution_time += execution_time
            self._total_queue_wait_time += queue_wait_time
            self._execution_times.append(execution_time)
            self._queue_wait_times.append(queue_wait_time)

    def record_task_cancelled(self) -> None:
        """记录任务取消"""
        with self._lock:
            self._tasks_cancelled += 1

    def record_cleanup(self, cleanup_time: float, cleaned_count: int) -> None:
        """
        记录清理操作

        Args:
            cleanup_time: 清理耗时（秒）
            cleaned_count: 清理的任务数量
        """
        with self._lock:
            self._cleanup_count += cleaned_count
            self._total_cleanup_time += cleanup_time
            self._cleanup_times.append(cleanup_time)

    def get_metrics(self) -> Dict[str, Any]:
        """
        获取当前性能指标

        Returns:
            Dict[str, Any]: 性能指标字典
        """
        with self._lock:
            uptime = time.time() - self._start_time
            completed = self._tasks_completed
            total = self._tasks_submitted

            avg_execution_time = self._total_execution_time / completed if completed > 0 else 0.0
            avg_queue_wait_time = self._total_queue_wait_time / completed if completed > 0 else 0.0

            recent_execution_times = (
                sum(self._execution_times) / len(self._execution_times)
                if self._execution_times
                else 0.0
            )
            recent_queue_wait_times = (
                sum(self._queue_wait_times) / len(self._queue_wait_times)
                if self._queue_wait_times
                else 0.0
            )

            return {
                "uptime_seconds": uptime,
                "tasks_submitted": self._tasks_submitted,
                "tasks_completed": self._tasks_completed,
                "tasks_failed": self._tasks_failed,
                "tasks_cancelled": self._tasks_cancelled,
                "tasks_in_progress": self._tasks_submitted
                - self._tasks_completed
                - self._tasks_failed
                - self._tasks_cancelled,
                "success_rate": (completed / total if total > 0 else 0.0),
                "failure_rate": (self._tasks_failed / total if total > 0 else 0.0),
                "avg_execution_time_seconds": avg_execution_time,
                "avg_queue_wait_time_seconds": avg_queue_wait_time,
                "recent_avg_execution_time_seconds": recent_execution_times,
                "recent_avg_queue_wait_time_seconds": recent_queue_wait_times,
                "total_execution_time_seconds": self._total_execution_time,
                "total_queue_wait_time_seconds": self._total_queue_wait_time,
                "cleanup_count": self._cleanup_count,
                "total_cleanup_time_seconds": self._total_cleanup_time,
                "avg_cleanup_time_seconds": (
                    self._total_cleanup_time / self._cleanup_count
                    if self._cleanup_count > 0
                    else 0.0
                ),
                "tasks_per_second": (self._tasks_submitted / uptime if uptime > 0 else 0.0),
            }

    def get_percentiles(self, percentiles: List[int] = None) -> Dict[str, float]:
        """
        获取执行时间百分位数

        Args:
            percentiles: 百分位列表，默认 [50, 75, 90, 95, 99]

        Returns:
            Dict[str, float]: 百分位数据
        """
        if percentiles is None:
            percentiles = [50, 75, 90, 95, 99]

        with self._lock:
            if not self._execution_times:
                return {f"p{p}": 0.0 for p in percentiles}

            sorted_times = sorted(self._execution_times)
            n = len(sorted_times)

            result = {}
            for p in percentiles:
                idx = int(n * p / 100)
                if idx >= n:
                    idx = n - 1
                result[f"p{p}"] = sorted_times[idx]

            return result

    def reset(self) -> None:
        """重置所有指标"""
        with self._lock:
            self._tasks_submitted = 0
            self._tasks_completed = 0
            self._tasks_failed = 0
            self._tasks_cancelled = 0
            self._total_execution_time = 0.0
            self._total_queue_wait_time = 0.0
            self._total_cleanup_time = 0.0
            self._cleanup_count = 0
            self._execution_times.clear()
            self._queue_wait_times.clear()
            self._cleanup_times.clear()
            self._start_time = time.time()


class SystemHealthMonitor:
    """系统健康状态监控器"""

    HEALTH_STATUS_GREEN = "green"
    HEALTH_STATUS_YELLOW = "yellow"
    HEALTH_STATUS_RED = "red"

    def __init__(self, logger: logging.Logger = None):
        """
        初始化系统健康监控器

        Args:
            logger: 日志记录器
        """
        self.logger = logger or logging.getLogger(__name__)

        self._health_checks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

        self._register_default_health_checks()

    def _register_default_health_checks(self) -> None:
        """注册默认健康检查"""
        self.register_health_check(
            "queue_size",
            lambda m: m.get("tasks_in_progress", 0),
            threshold=1000,
            status_warning=800,
            status_critical=950,
        )

        self.register_health_check(
            "failure_rate",
            lambda m: m.get("failure_rate", 0) * 100,
            threshold=10,
            status_warning=5,
            status_critical=10,
        )

        self.register_health_check(
            "avg_execution_time",
            lambda m: m.get("avg_execution_time_seconds", 0),
            threshold=60,
            status_warning=30,
            status_critical=60,
        )

    def register_health_check(
        self,
        name: str,
        value_func: callable,
        threshold: float = None,
        status_warning: float = None,
        status_critical: float = None,
    ) -> None:
        """
        注册健康检查项

        Args:
            name: 检查项名称
            value_func: 获取值的函数，接受metrics字典
            threshold: 默认阈值
            status_warning: 警告状态阈值
            status_critical: 严重状态阈值
        """
        with self._lock:
            self._health_checks[name] = {
                "value_func": value_func,
                "threshold": threshold,
                "status_warning": status_warning,
                "status_critical": status_critical,
                "current_value": None,
                "status": self.HEALTH_STATUS_GREEN,
            }

    def update_health_status(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新健康状态

        Args:
            metrics: 性能指标字典

        Returns:
            Dict[str, Any]: 健康状态信息
        """
        with self._lock:
            overall_status = self.HEALTH_STATUS_GREEN
            check_results = {}

            for name, check in self._health_checks.items():
                try:
                    value = check["value_func"](metrics)
                    check["current_value"] = value

                    if check["status_critical"] and value >= check["status_critical"]:
                        check["status"] = self.HEALTH_STATUS_RED
                        overall_status = self.HEALTH_STATUS_RED
                    elif check["status_warning"] and value >= check["status_warning"]:
                        if overall_status != self.HEALTH_STATUS_RED:
                            overall_status = self.HEALTH_STATUS_YELLOW
                        check["status"] = self.HEALTH_STATUS_YELLOW
                    else:
                        check["status"] = self.HEALTH_STATUS_GREEN

                    check_results[name] = {
                        "value": value,
                        "status": check["status"],
                        "warning_threshold": check["status_warning"],
                        "critical_threshold": check["status_critical"],
                    }

                except Exception as e:
                    self.logger.warning(f"健康检查 {name} 执行失败: {e}")
                    check_results[name] = {
                        "value": None,
                        "status": self.HEALTH_STATUS_RED,
                        "error": str(e),
                    }
                    overall_status = self.HEALTH_STATUS_RED

            result = {
                "overall_status": overall_status,
                "checks": check_results,
                "timestamp": time.time(),
            }

            if overall_status == self.HEALTH_STATUS_RED:
                self.logger.error(f"系统健康状态: RED - {check_results}")
            elif overall_status == self.HEALTH_STATUS_YELLOW:
                self.logger.warning(f"系统健康状态: YELLOW - {check_results}")

            return result

    def get_health_status(self) -> Dict[str, Any]:
        """
        获取当前健康状态

        Returns:
            Dict[str, Any]: 健康状态信息
        """
        with self._lock:
            return {
                name: {
                    "current_value": check.get("current_value"),
                    "status": check["status"],
                }
                for name, check in self._health_checks.items()
            }
