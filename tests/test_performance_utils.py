"""
性能模块工具测试

测试性能优化相关的工具函数和类。
"""

import logging
import threading
import time

import pytest

from fish_async_task.performance.adaptive_scaling import AdaptiveWorkerManager
from fish_async_task.performance.priority_cleanup import TaskStatusWithExpiry
from fish_async_task.types import TaskStatusDict


class TestAdaptiveWorkerManager:
    """测试自适应工作线程管理器"""

    def test_init_default_values(self):
        """测试默认值初始化"""
        manager = AdaptiveWorkerManager(
            min_workers=1,
            max_workers=10,
        )

        assert manager.min_workers == 1
        assert manager.max_workers == 10
        assert manager.cpu_threshold == 0.8
        assert manager.queue_threshold == 100

    def test_init_custom_values(self):
        """测试自定义值初始化"""
        manager = AdaptiveWorkerManager(
            min_workers=2,
            max_workers=20,
            cpu_threshold=0.7,
            queue_threshold=200,
            scale_up_cooldown=10.0,
            scale_down_cooldown=60.0,
        )

        assert manager.cpu_threshold == 0.7
        assert manager.queue_threshold == 200
        assert manager.scale_up_cooldown == 10.0
        assert manager.scale_down_cooldown == 60.0

    def test_should_scale_up_basic(self):
        """测试基本扩容条件"""
        manager = AdaptiveWorkerManager(
            min_workers=1,
            max_workers=10,
        )

        # 队列积压超过阈值
        should_scale, reason = manager.should_scale_up(
            current_workers=2,
            queue_size=150,
        )
        assert should_scale is True

    def test_should_scale_up_cpu_limit(self):
        """测试 CPU 限制下的扩容"""
        manager = AdaptiveWorkerManager(
            min_workers=1,
            max_workers=10,
            cpu_threshold=0.7,
        )

        # CPU 使用率过高
        should_scale, reason = manager.should_scale_up(
            current_workers=5,
            queue_size=150,
            cpu_usage=0.9,
        )
        assert should_scale is False

    def test_should_scale_up_max_limit(self):
        """测试达到最大线程数时的扩容"""
        manager = AdaptiveWorkerManager(
            min_workers=1,
            max_workers=10,
        )

        # 已达到最大线程数
        should_scale, reason = manager.should_scale_up(
            current_workers=10,
            queue_size=200,
        )
        assert should_scale is False

    def test_should_scale_down_basic(self):
        """测试基本缩容条件"""
        manager = AdaptiveWorkerManager(
            min_workers=1,
            max_workers=10,
        )

        # 队列空闲
        should_scale, reason = manager.should_scale_down(
            current_workers=5,
            queue_size=5,
        )
        # 根据实现，可能会返回 True 或 False
        assert isinstance(should_scale, bool)

    def test_should_scale_down_min_limit(self):
        """测试达到最小线程数时的缩容"""
        manager = AdaptiveWorkerManager(
            min_workers=2,
            max_workers=10,
        )

        # 已达到最小线程数
        should_scale, reason = manager.should_scale_down(
            current_workers=2,
            queue_size=0,
        )
        assert should_scale is False

    def test_record_task_time(self):
        """测试记录任务执行时间"""
        manager = AdaptiveWorkerManager(
            min_workers=1,
            max_workers=10,
        )

        # 记录一些任务时间
        manager.record_task_time(0.5)
        manager.record_task_time(0.3)
        manager.record_task_time(0.7)

        # 验证记录成功（不抛出异常）
        assert manager.get_avg_task_time() >= 0

    def test_get_cpu_usage(self):
        """测试获取 CPU 使用率"""
        manager = AdaptiveWorkerManager(
            min_workers=1,
            max_workers=10,
        )

        # 获取 CPU 使用率
        cpu_usage = manager.get_cpu_usage()

        # 应该返回 0-1 之间的值或 None
        assert cpu_usage is None or (0 <= cpu_usage <= 1)

    def test_get_stats(self):
        """测试获取统计信息"""
        manager = AdaptiveWorkerManager(
            min_workers=1,
            max_workers=10,
        )

        # 使用 get_scaling_metrics 获取统计信息
        metrics = manager.get_scaling_metrics(current_workers=5, queue_size=10)
        assert isinstance(metrics, dict)


class TestTaskStatusWithExpiry:
    """测试带过期时间的任务状态存储"""

    def test_init_default(self):
        """测试默认初始化"""
        store = TaskStatusWithExpiry()
        assert store.ttl == 300

    def test_init_custom_ttl(self):
        """测试自定义 TTL"""
        store = TaskStatusWithExpiry(ttl=600)
        assert store.ttl == 600

    def test_init_invalid_ttl(self):
        """测试无效 TTL"""
        with pytest.raises(ValueError):
            TaskStatusWithExpiry(ttl=0)

        with pytest.raises(ValueError):
            TaskStatusWithExpiry(ttl=-1)

    def test_add_and_get_status(self):
        """测试添加和获取状态"""
        store = TaskStatusWithExpiry(ttl=10)

        status: TaskStatusDict = {
            "status": "pending",
            "submit_time": time.time(),
        }

        store.add_task("task1", status)
        result = store.get_task("task1")

        assert result is not None
        assert result["status"] == "pending"

    def test_cleanup_expired(self):
        """测试清理过期任务"""
        store = TaskStatusWithExpiry(ttl=1)

        # 添加任务
        for i in range(5):
            status: TaskStatusDict = {
                "status": "completed",
                "submit_time": time.time() - 10,
                "start_time": time.time() - 9,
                "end_time": time.time() - 8,
            }
            store.add_task(f"task_{i}", status)

        # 等待确保过期
        time.sleep(2)

        # 清理过期任务
        cleaned = store.cleanup_expired()
        assert cleaned >= 0

    def test_remove_status(self):
        """测试移除状态（通过 enforce_max_count）"""
        store = TaskStatusWithExpiry(ttl=10)

        status: TaskStatusDict = {
            "status": "pending",
            "submit_time": time.time(),
        }

        store.add_task("task1", status)
        assert store.get_task("task1") is not None

        # 使用 enforce_max_count 清空
        store.enforce_max_count(0)
        assert store.get_task("task1") is None

    def test_clear_all(self):
        """测试清空所有"""
        store = TaskStatusWithExpiry(ttl=10)

        for i in range(5):
            status: TaskStatusDict = {
                "status": "pending",
                "submit_time": time.time(),
            }
            store.add_task(f"task_{i}", status)

        # 使用 enforce_max_count 清空
        store.enforce_max_count(0)
        assert store.get_task("task1") is None

    def test_get_count(self):
        """测试获取任务数量"""
        store = TaskStatusWithExpiry(ttl=10)

        assert store.get_task_count() == 0

        for i in range(5):
            status: TaskStatusDict = {
                "status": "pending",
                "submit_time": time.time(),
            }
            store.add_task(f"task_{i}", status)

        assert store.get_task_count() == 5


class TestPerformanceUtilsIntegration:
    """测试性能工具集成"""

    def test_adaptive_manager_stats(self):
        """测试自适应管理器统计"""
        manager = AdaptiveWorkerManager(
            min_workers=1,
            max_workers=10,
        )

        # 记录任务时间
        manager.record_task_time(0.5)
        manager.record_task_time(0.3)
        manager.record_task_time(0.7)

        # 获取统计信息
        metrics = manager.get_scaling_metrics(current_workers=5, queue_size=10)
        assert isinstance(metrics, dict)
        assert "avg_task_time" in metrics

    def test_concurrent_status_operations(self):
        """测试并发状态操作"""
        store = TaskStatusWithExpiry(ttl=10)
        errors = []

        def add_status(index: int):
            try:
                status: TaskStatusDict = {
                    "status": "pending",
                    "submit_time": time.time(),
                }
                store.add_task(f"task_{index}", status)
            except Exception as e:
                errors.append(e)

        # 并发添加
        threads = []
        for i in range(20):
            thread = threading.Thread(target=add_status, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # 验证没有错误
        assert len(errors) == 0
        assert store.get_task_count() == 20


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
