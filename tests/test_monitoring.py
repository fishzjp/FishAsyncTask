"""
性能监控模块测试
"""

import pytest
import time

from fish_async_task.performance.monitoring import (
    PerformanceMetrics,
    SystemHealthMonitor,
)


class TestPerformanceMetrics:
    """测试 PerformanceMetrics 类"""

    def test_init_default(self):
        """测试默认初始化"""
        metrics = PerformanceMetrics()
        assert metrics._max_history == 1000
        assert metrics._tasks_submitted == 0

    def test_init_custom_max_history(self):
        """测试自定义历史记录数"""
        metrics = PerformanceMetrics(max_history=100)
        assert metrics._max_history == 100

    def test_record_task_submitted(self):
        """测试记录任务提交"""
        metrics = PerformanceMetrics()
        metrics.record_task_submitted()
        assert metrics._tasks_submitted == 1
        metrics.record_task_submitted()
        assert metrics._tasks_submitted == 2

    def test_record_task_completed(self):
        """测试记录任务完成"""
        metrics = PerformanceMetrics()
        metrics.record_task_completed(1.0, 0.5)
        assert metrics._tasks_completed == 1
        assert metrics._total_execution_time == 1.0
        assert metrics._total_queue_wait_time == 0.5

    def test_record_task_failed(self):
        """测试记录任务失败"""
        metrics = PerformanceMetrics()
        metrics.record_task_failed(0.5, 0.2)
        assert metrics._tasks_failed == 1
        assert metrics._total_execution_time == 0.5

    def test_record_task_cancelled(self):
        """测试记录任务取消"""
        metrics = PerformanceMetrics()
        metrics.record_task_cancelled()
        assert metrics._tasks_cancelled == 1

    def test_record_cleanup(self):
        """测试记录清理操作"""
        metrics = PerformanceMetrics()
        metrics.record_cleanup(0.5, 10)
        assert metrics._cleanup_count == 10
        assert metrics._total_cleanup_time == 0.5

    def test_get_metrics_empty(self):
        """测试获取空指标"""
        metrics = PerformanceMetrics()
        time.sleep(0.01)  # 确保有 uptime
        result = metrics.get_metrics()
        assert result["tasks_submitted"] == 0
        assert result["tasks_completed"] == 0
        assert result["success_rate"] == 0.0
        assert result["uptime_seconds"] >= 0.01

    def test_get_metrics_with_data(self):
        """测试获取有数据的指标"""
        metrics = PerformanceMetrics()
        metrics.record_task_submitted()
        metrics.record_task_submitted()
        metrics.record_task_submitted()  # 3个提交的任务
        metrics.record_task_completed(1.0, 0.5)
        metrics.record_task_completed(2.0, 0.5)
        metrics.record_task_failed(0.5, 0.5)

        result = metrics.get_metrics()
        assert result["tasks_submitted"] == 3
        assert result["tasks_completed"] == 2
        assert result["tasks_failed"] == 1
        assert result["success_rate"] == 2 / 3
        assert result["failure_rate"] == 1 / 3
        # 总执行时间 = 1.0 + 2.0 + 0.5 = 3.5
        # avg_execution_time = 3.5 / 2 (只计算完成的任务)
        assert result["avg_execution_time_seconds"] == 1.75
        assert result["avg_queue_wait_time_seconds"] == (1.5 / 2)

    def test_get_percentiles_empty(self):
        """测试获取空百分位数"""
        metrics = PerformanceMetrics()
        result = metrics.get_percentiles()
        assert result["p50"] == 0.0
        assert result["p95"] == 0.0

    def test_get_percentiles_with_data(self):
        """测试获取有数据的百分位数"""
        metrics = PerformanceMetrics()
        for i in range(100):
            metrics.record_task_completed(float(i), 0.0)

        result = metrics.get_percentiles([50, 90, 95])
        assert 0 <= result["p50"] <= 100
        assert 0 <= result["p90"] <= 100
        assert 0 <= result["p95"] <= 100

    def test_get_percentiles_custom(self):
        """测试自定义百分位数"""
        metrics = PerformanceMetrics()
        for i in range(10):
            metrics.record_task_completed(float(i), 0.0)

        result = metrics.get_percentiles([25, 50, 75])
        assert "p25" in result
        assert "p50" in result
        assert "p75" in result

    def test_reset(self):
        """测试重置指标"""
        metrics = PerformanceMetrics()
        metrics.record_task_submitted()
        metrics.record_task_completed(1.0, 0.5)

        metrics.reset()
        assert metrics._tasks_submitted == 0
        assert metrics._tasks_completed == 0
        assert metrics._total_execution_time == 0.0
        assert len(metrics._execution_times) == 0

    def test_history_limit(self):
        """测试历史记录限制"""
        metrics = PerformanceMetrics(max_history=10)
        for i in range(20):
            metrics.record_task_completed(float(i), 0.0)

        assert len(metrics._execution_times) == 10


class TestSystemHealthMonitor:
    """测试 SystemHealthMonitor 类"""

    def test_init(self):
        """测试初始化"""
        monitor = SystemHealthMonitor()
        assert "queue_size" in monitor._health_checks
        assert "failure_rate" in monitor._health_checks
        assert "avg_execution_time" in monitor._health_checks

    def test_register_health_check(self):
        """测试注册健康检查"""
        monitor = SystemHealthMonitor()
        monitor.register_health_check(
            "test_check",
            lambda m: m.get("test_value", 0),
            threshold=100,
            status_warning=80,
            status_critical=95,
        )

        assert "test_check" in monitor._health_checks

    def test_update_health_status_green(self):
        """测试绿色健康状态"""
        monitor = SystemHealthMonitor()
        metrics = {
            "tasks_in_progress": 100,
            "failure_rate": 0.01,
            "avg_execution_time_seconds": 1.0,
        }

        result = monitor.update_health_status(metrics)
        assert result["overall_status"] == SystemHealthMonitor.HEALTH_STATUS_GREEN

    def test_update_health_status_yellow(self):
        """测试黄色健康状态"""
        monitor = SystemHealthMonitor()
        metrics = {
            "tasks_in_progress": 850,  # 超过警告阈值 800
            "failure_rate": 0.01,
            "avg_execution_time_seconds": 1.0,
        }

        result = monitor.update_health_status(metrics)
        assert result["overall_status"] == SystemHealthMonitor.HEALTH_STATUS_YELLOW

    def test_update_health_status_red(self):
        """测试红色健康状态"""
        monitor = SystemHealthMonitor()
        metrics = {
            "tasks_in_progress": 975,  # 超过严重阈值 950
            "failure_rate": 0.01,
            "avg_execution_time_seconds": 1.0,
        }

        result = monitor.update_health_status(metrics)
        assert result["overall_status"] == SystemHealthMonitor.HEALTH_STATUS_RED

    def test_update_health_status_multiple_checks(self):
        """测试多个健康检查"""
        monitor = SystemHealthMonitor()
        metrics = {
            "tasks_in_progress": 500,
            "failure_rate": 0.08,  # 超过警告阈值 5%
            "avg_execution_time_seconds": 1.0,
        }

        result = monitor.update_health_status(metrics)
        assert result["overall_status"] == SystemHealthMonitor.HEALTH_STATUS_YELLOW

    def test_update_health_status_exception(self):
        """测试健康检查异常"""
        monitor = SystemHealthMonitor()

        def failing_check(m):
            raise ValueError("Test error")

        monitor.register_health_check("failing_check", failing_check)
        metrics = {}

        result = monitor.update_health_status(metrics)
        assert result["overall_status"] == SystemHealthMonitor.HEALTH_STATUS_RED
        assert "failing_check" in result["checks"]
        assert result["checks"]["failing_check"]["status"] == SystemHealthMonitor.HEALTH_STATUS_RED

    def test_get_health_status(self):
        """测试获取健康状态"""
        monitor = SystemHealthMonitor()
        status = monitor.get_health_status()
        assert "queue_size" in status
        assert "failure_rate" in status
        assert "avg_execution_time" in status

    def test_health_status_constants(self):
        """测试健康状态常量"""
        assert SystemHealthMonitor.HEALTH_STATUS_GREEN == "green"
        assert SystemHealthMonitor.HEALTH_STATUS_YELLOW == "yellow"
        assert SystemHealthMonitor.HEALTH_STATUS_RED == "red"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
