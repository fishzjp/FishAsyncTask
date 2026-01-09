"""自适应工作线程管理测试

测试 AdaptiveWorkerManager 类的扩展/缩减决策、冷却期机制、CPU 监控等功能。
"""

import time
from typing import Any, Dict

import pytest

from fish_async_task.performance.adaptive_scaling import AdaptiveWorkerManager


class TestAdaptiveWorkerManager:
    """测试 AdaptiveWorkerManager 类的基本功能"""

    def test_init_default_params(self):
        """测试使用默认参数初始化"""
        manager = AdaptiveWorkerManager()

        assert manager.min_workers == 2
        assert manager.max_workers == 10
        assert manager.scale_up_cooldown == 30.0
        assert manager.scale_down_cooldown == 60.0
        assert manager.cpu_threshold == 0.8
        assert manager.queue_threshold == 100

    def test_init_custom_params(self):
        """测试使用自定义参数初始化"""
        manager = AdaptiveWorkerManager(
            min_workers=5,
            max_workers=20,
            scale_up_cooldown=10.0,
            scale_down_cooldown=30.0,
            cpu_threshold=0.7,
            queue_threshold=200,
        )

        assert manager.min_workers == 5
        assert manager.max_workers == 20
        assert manager.scale_up_cooldown == 10.0
        assert manager.scale_down_cooldown == 30.0
        assert manager.cpu_threshold == 0.7
        assert manager.queue_threshold == 200

    def test_scale_up_decision(self):
        """测试扩展决策逻辑"""
        manager = AdaptiveWorkerManager(
            min_workers=2, max_workers=10, scale_up_cooldown=1.0, queue_threshold=10
        )

        current_workers = 5
        queue_size = 50  # 队列大小超过阈值

        # 记录扩展决策
        should_scale, reason = manager.should_scale_up(
            current_workers=current_workers, queue_size=queue_size
        )

        # 应该扩展（队列大）
        assert should_scale is True
        assert "队列大小" in reason or "queue" in reason.lower()

    def test_scale_up_at_max_workers(self):
        """测试达到最大工作线程数时不扩展"""
        manager = AdaptiveWorkerManager(
            min_workers=2, max_workers=10, queue_threshold=10
        )

        current_workers = 10  # 已达到最大值
        queue_size = 100

        should_scale, reason = manager.should_scale_up(
            current_workers=current_workers, queue_size=queue_size
        )

        # 不应该扩展（已达最大值）
        assert should_scale is False
        assert "最大" in reason or "max" in reason.lower()

    def test_scale_up_cooldown_period(self):
        """测试扩展冷却期"""
        manager = AdaptiveWorkerManager(
            scale_up_cooldown=0.5, queue_threshold=10  # 500ms 冷却期
        )

        current_workers = 5
        queue_size = 50

        # 第一次扩展决策
        should_scale1, _ = manager.should_scale_up(current_workers, queue_size)
        assert should_scale1 is True

        # 立即再次检查（在冷却期内）
        should_scale2, _ = manager.should_scale_up(current_workers, queue_size)
        assert should_scale2 is False  # 冷却期内不扩展

        # 等待冷却期结束
        time.sleep(0.6)

        # 冷却期后应该可以扩展
        should_scale3, _ = manager.should_scale_up(current_workers, queue_size)
        assert should_scale3 is True

    def test_scale_down_decision(self):
        """测试缩减决策逻辑"""
        manager = AdaptiveWorkerManager(
            min_workers=2, max_workers=10, scale_down_cooldown=1.0, queue_threshold=10
        )

        current_workers = 8
        queue_size = 2  # 队列很小

        # 记录任务执行时间（快速完成任务）
        for _ in range(10):
            manager.record_task_time(0.01)  # 10ms

        should_scale, reason = manager.should_scale_down(
            current_workers=current_workers, queue_size=queue_size
        )

        # 应该缩减（队列小，任务快）
        assert should_scale is True
        assert "队列" in reason or "queue" in reason.lower() or "任务" in reason

    def test_scale_down_at_min_workers(self):
        """测试达到最小工作线程数时不缩减"""
        manager = AdaptiveWorkerManager(
            min_workers=2, max_workers=10, queue_threshold=10
        )

        current_workers = 2  # 已达到最小值
        queue_size = 0

        # 记录任务执行时间
        for _ in range(10):
            manager.record_task_time(0.01)

        should_scale, reason = manager.should_scale_down(
            current_workers=current_workers, queue_size=queue_size
        )

        # 不应该缩减（已达最小值）
        assert should_scale is False
        assert "最小" in reason or "min" in reason.lower()

    def test_scale_down_cooldown_period(self):
        """测试缩减冷却期"""
        manager = AdaptiveWorkerManager(
            scale_down_cooldown=0.5, queue_threshold=10  # 500ms 冷却期
        )

        current_workers = 8
        queue_size = 2

        # 记录任务执行时间
        for _ in range(10):
            manager.record_task_time(0.01)

        # 第一次缩减决策
        should_scale1, _ = manager.should_scale_down(current_workers, queue_size)
        assert should_scale1 is True

        # 立即再次检查（在冷却期内）
        should_scale2, _ = manager.should_scale_down(current_workers, queue_size)
        assert should_scale2 is False  # 冷却期内不缩减

        # 等待冷却期结束
        time.sleep(0.6)

        # 冷却期后应该可以缩减
        should_scale3, _ = manager.should_scale_down(current_workers, queue_size)
        assert should_scale3 is True

    def test_task_time_tracking(self):
        """测试任务执行时间跟踪"""
        manager = AdaptiveWorkerManager()

        # 记录一些任务执行时间
        task_times = [0.1, 0.2, 0.15, 0.25, 0.3]
        for t in task_times:
            manager.record_task_time(t)

        avg_time = manager.get_avg_task_time()

        # 验证平均时间计算正确
        expected_avg = sum(task_times) / len(task_times)
        assert abs(avg_time - expected_avg) < 0.001

    def test_avg_task_time_initial_state(self):
        """测试初始状态下的平均任务时间"""
        manager = AdaptiveWorkerManager()

        # 没有记录任务时，应该返回 0 或 None
        avg_time = manager.get_avg_task_time()
        assert avg_time == 0.0

    def test_cpu_usage_with_psutil(self):
        """测试 CPU 使用率监控（psutil 可用时）"""
        manager = AdaptiveWorkerManager()

        cpu_usage = manager.get_cpu_usage()

        # CPU 使用率应该在 0-1 之间（如果 psutil 可用）
        # 或者返回 None（如果 psutil 不可用）
        if cpu_usage is not None:
            assert 0.0 <= cpu_usage <= 1.0

    def test_cpu_usage_graceful_degradation(self):
        """测试 CPU 监控优雅降级（psutil 不可用时）"""
        # 这个测试验证当 psutil 不可用时的行为
        # 在实际环境中，如果安装了 psutil，会返回实际值
        # 如果没有安装，会返回 None 或回退值
        manager = AdaptiveWorkerManager()

        cpu_usage = manager.get_cpu_usage()

        # 应该不抛出异常
        # 如果 psutil 不可用，应该返回 None
        assert cpu_usage is None or (0.0 <= cpu_usage <= 1.0)

    def test_scaling_metrics_collection(self):
        """测试扩展指标收集"""
        manager = AdaptiveWorkerManager(min_workers=2, max_workers=10)

        # 记录一些任务执行时间
        for i in range(5):
            manager.record_task_time(0.1 * (i + 1))

        # 触发一次扩展决策（记录时间戳）
        manager.should_scale_up(current_workers=5, queue_size=100)

        metrics = manager.get_scaling_metrics(current_workers=5, queue_size=100)

        # 验证指标包含所有必要字段
        assert "current_workers" in metrics
        assert "avg_task_time" in metrics
        assert "cpu_usage" in metrics
        assert "last_scale_up_time" in metrics
        assert "last_scale_down_time" in metrics
        assert "queue_size" in metrics

        # 验证指标值
        assert metrics["current_workers"] == 5
        assert metrics["avg_task_time"] > 0
        assert metrics["queue_size"] == 100

    def test_scale_up_considers_cpu_usage(self):
        """测试扩展决策考虑 CPU 使用率"""
        manager = AdaptiveWorkerManager(
            max_workers=10, cpu_threshold=0.7, queue_threshold=10  # 70% CPU 阈值
        )

        # 这个测试需要模拟高 CPU 使用率
        # 实际环境中，我们只能测试逻辑
        current_workers = 5
        queue_size = 100  # 大队列

        # 如果 CPU 使用率高，不应该扩展
        # 注意：实际 CPU 使用率由 psutil 提供，这里只测试逻辑
        should_scale, reason = manager.should_scale_up(
            current_workers=current_workers,
            queue_size=queue_size,
            cpu_usage=0.9,  # 模拟 90% CPU 使用率
        )

        # CPU 使用率高，不应该扩展
        assert should_scale is False
        assert "CPU" in reason or "cpu" in reason.lower()

    def test_scale_up_with_low_cpu(self):
        """测试低 CPU 使用率时可以扩展"""
        manager = AdaptiveWorkerManager(
            max_workers=10, cpu_threshold=0.7, queue_threshold=10
        )

        current_workers = 5
        queue_size = 100

        should_scale, reason = manager.should_scale_up(
            current_workers=current_workers,
            queue_size=queue_size,
            cpu_usage=0.3,  # 低 CPU 使用率
        )

        # CPU 使用率低，应该扩展
        assert should_scale is True
        assert "队列" in reason or "queue" in reason.lower()


class TestAdaptiveScalingIntegration:
    """测试自适应扩展的集成场景"""

    def test_workload_increase_scenario(self):
        """测试工作负载增加场景"""
        manager = AdaptiveWorkerManager(
            min_workers=2, max_workers=10, scale_up_cooldown=1.0, queue_threshold=10
        )

        current_workers = 2

        # 模拟工作负载增加
        for i in range(5):
            queue_size = 10 * (i + 1)  # 队列从 10 增加到 50

            should_scale, _ = manager.should_scale_up(
                current_workers=current_workers, queue_size=queue_size, cpu_usage=0.4
            )

            if should_scale and current_workers < manager.max_workers:
                current_workers += 1

        # 验证工作线程增加
        assert current_workers > 2
        assert current_workers <= 10

    def test_workload_decrease_scenario(self):
        """测试工作负载减少场景"""
        manager = AdaptiveWorkerManager(
            min_workers=2, max_workers=10, scale_down_cooldown=1.0, queue_threshold=10
        )

        current_workers = 8

        # 记录一些快速任务
        for _ in range(20):
            manager.record_task_time(0.01)

        # 模拟工作负载减少
        for i in range(5):
            queue_size = max(0, 10 - 2 * i)  # 队列从 10 减少到 0

            should_scale, _ = manager.should_scale_down(
                current_workers=current_workers, queue_size=queue_size
            )

            if should_scale and current_workers > manager.min_workers:
                current_workers -= 1
                time.sleep(1.1)  # 等待冷却期

        # 验证工作线程减少
        assert current_workers < 8
        assert current_workers >= 2

    def test_steady_workload_scenario(self):
        """测试稳定工作负载场景（不扩展也不缩减）"""
        manager = AdaptiveWorkerManager(
            min_workers=2, max_workers=10, queue_threshold=50
        )

        current_workers = 5
        queue_size = 25  # 适中的队列大小

        # 不应该扩展（队列不够大）
        should_scale_up, _ = manager.should_scale_up(
            current_workers=current_workers, queue_size=queue_size
        )
        assert should_scale_up is False

        # 不应该缩减（队列不够小，且没有快速任务记录）
        should_scale_down, _ = manager.should_scale_down(
            current_workers=current_workers, queue_size=queue_size
        )
        assert should_scale_down is False


class TestAdaptiveScalingCpuMonitoring:
    """测试 CPU 监控功能"""

    def test_cpu_usage_available_when_psutil_installed(self):
        """测试 psutil 可用时能获取 CPU 使用率"""
        manager = AdaptiveWorkerManager()

        cpu_usage = manager.get_cpu_usage()

        # 如果 psutil 可用，应该返回一个值
        # 如果不可用，应该返回 None
        if cpu_usage is not None:
            assert isinstance(cpu_usage, float)
            assert 0.0 <= cpu_usage <= 1.0
        else:
            # psutil 不可用时的降级行为
            assert cpu_usage is None

    def test_scale_decision_without_psutil(self):
        """测试没有 psutil 时的扩展决策（基于队列）"""
        manager = AdaptiveWorkerManager(max_workers=10, queue_threshold=10)

        current_workers = 5
        queue_size = 100

        # 即使没有 CPU 数据，也应该能做出决策
        should_scale, reason = manager.should_scale_up(
            current_workers=current_workers,
            queue_size=queue_size,
            cpu_usage=None,  # 模拟 psutil 不可用
        )

        # 应该基于队列大小扩展
        assert should_scale is True
        assert "队列" in reason or "queue" in reason.lower()
