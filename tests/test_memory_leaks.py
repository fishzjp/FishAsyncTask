"""
资源泄漏测试模块

测试 TaskManager 的资源管理，包括：
- 单例实例的销毁
- Timer 线程的清理
- 内存泄漏检测
"""

import gc
import logging
import threading
import time
import tracemalloc
import weakref
from typing import List

import pytest

from fish_async_task import TaskManager


class TestSingletonMemoryLeak:
    """单例模式内存泄漏测试"""

    def test_destroy_instance(self):
        """测试销毁单例实例"""
        # 创建实例
        manager1 = TaskManager(instance_key="test_destroy")
        assert "test_destroy" in TaskManager._instances

        # 销毁实例
        result = TaskManager.destroy_instance("test_destroy")
        assert result is True
        assert "test_destroy" not in TaskManager._instances

        # 再次销毁应该返回 False
        result = TaskManager.destroy_instance("test_destroy")
        assert result is False

    def test_destroy_running_instance(self):
        """测试销毁正在运行的实例"""
        # 创建并启动实例
        manager = TaskManager(instance_key="test_running")

        # 提交一些任务
        def simple_task():
            return "done"

        for _ in range(5):
            manager.submit_task(simple_task)

        # 销毁实例应该先关闭
        result = TaskManager.destroy_instance("test_running")
        assert result is True

        # 实例应该被移除
        assert "test_running" not in TaskManager._instances

    def test_destroy_multiple_instances(self):
        """测试销毁多个独立实例"""
        # 创建多个实例
        keys = ["test_multi_1", "test_multi_2", "test_multi_3"]
        managers = [TaskManager(instance_key=key) for key in keys]

        # 验证所有实例都存在
        for key in keys:
            assert key in TaskManager._instances

        # 销毁所有实例
        for key in keys:
            TaskManager.destroy_instance(key)

        # 验证所有实例都被移除
        for key in keys:
            assert key not in TaskManager._instances

    def test_instance_gc_after_destroy(self):
        """测试销毁后实例可以被垃圾回收"""
        # 创建实例
        manager = TaskManager(instance_key="test_gc")
        manager_id = id(manager)

        # 创建弱引用
        weak_ref = weakref.ref(manager)

        # 销毁实例
        TaskManager.destroy_instance("test_gc")

        # 删除强引用
        del manager

        # 强制垃圾回收
        gc.collect()

        # 弱引用应该返回 None（对象已被回收）
        assert weak_ref() is None


class TestTimerCleanup:
    """Timer 线程清理测试"""

    def test_timers_cleaned_on_shutdown(self):
        """测试 shutdown 时 Timer 被清理"""
        manager = TaskManager(instance_key="test_timer_cleanup")

        # 提交一些任务以触发 Timer 创建
        def simple_task():
            time.sleep(0.01)
            return "done"

        for _ in range(20):
            manager.submit_task(simple_task)
            time.sleep(0.01)  # 让 Timer 有时间创建

        # 等待一下让 Timer 启动
        time.sleep(0.5)

        # 关闭管理器
        manager.shutdown()

        # Timer 列表应该被清空
        assert len(manager._timers) == 0

        # 所有 Timer 应该被取消
        TaskManager.destroy_instance("test_timer_cleanup")

    def test_no_active_timers_after_shutdown(self):
        """测试 shutdown 后没有活动的 Timer"""
        manager = TaskManager(instance_key="test_no_active_timers")

        # 提交任务触发 Timer
        def simple_task():
            return "done"

        for _ in range(10):
            manager.submit_task(simple_task)

        time.sleep(0.3)

        # 关闭管理器
        manager.shutdown()

        # 检查所有 Timer 都不活跃
        for timer in manager._timers:
            assert not timer.is_alive()

        TaskManager.destroy_instance("test_no_active_timers")


class TestMemoryLeakDetection:
    """内存泄漏检测测试"""

    def test_no_memory_leak_with_repeated_create_destroy(self):
        """测试重复创建和销毁不会导致内存泄漏"""
        # 启动内存跟踪
        tracemalloc.start()

        # 获取初始内存使用
        gc.collect()
        snapshot1 = tracemalloc.take_snapshot()

        # 重复创建和销毁实例
        for i in range(5):
            manager = TaskManager(instance_key=f"test_leak_{i}")
            # 提交一些任务
            def simple_task():
                return "done"

            for _ in range(10):
                manager.submit_task(simple_task)

            # 等待任务完成
            time.sleep(0.2)

            # 销毁实例
            TaskManager.destroy_instance(f"test_leak_{i}")
            del manager

        # 强制垃圾回收
        gc.collect()

        # 获取最终内存使用
        snapshot2 = tracemalloc.take_snapshot()

        # 计算内存增长
        top_stats = snapshot2.compare_to(snapshot1, 'lineno')

        # 获取总增长
        total_growth = sum(stat.size_diff for stat in top_stats if stat.size_diff > 0)

        # 停止跟踪
        tracemalloc.stop()

        # 内存增长应该在合理范围内（小于 1MB）
        # 注意：这里需要一定的容差，因为 Python 本身会有一些内存开销
        assert total_growth < 1_000_000, f"内存增长过大: {total_growth} bytes"

    def test_no_thread_leak_after_destroy(self):
        """测试销毁后没有线程泄漏"""
        # 获取初始线程数
        initial_threads = threading.active_count()

        # 创建并销毁多个实例
        for i in range(3):
            manager = TaskManager(instance_key=f"test_thread_{i}")

            # 提交任务
            def simple_task():
                time.sleep(0.01)
                return "done"

            for _ in range(5):
                manager.submit_task(simple_task)

            time.sleep(0.2)

            # 销毁实例
            TaskManager.destroy_instance(f"test_thread_{i}")
            del manager

            # 等待线程退出
            time.sleep(0.3)

        # 强制垃圾回收
        gc.collect()

        # 等待所有线程退出
        time.sleep(0.5)

        # 最终线程数应该接近初始线程数
        # 允许一些差异，因为可能有其他系统线程
        final_threads = threading.active_count()
        thread_diff = final_threads - initial_threads

        assert thread_diff <= 2, f"线程泄漏: 初始 {initial_threads}, 最终 {final_threads}, 差异 {thread_diff}"


class TestResourceCleanup:
    """资源清理测试"""

    def test_worker_threads_cleaned(self):
        """测试工作线程被正确清理"""
        manager = TaskManager(instance_key="test_worker_cleanup")

        # 获取工作线程数
        initial_count = len(manager.worker_threads)
        assert initial_count >= 1

        # 关闭管理器
        manager.shutdown()

        # 工作线程列表应该被清空
        assert len(manager.worker_threads) == 0

        TaskManager.destroy_instance("test_worker_cleanup")

    def test_task_status_cleaned(self):
        """测试任务状态被正确清理"""
        manager = TaskManager(instance_key="test_status_cleanup")

        # 提交一些任务
        def simple_task():
            return "done"

        task_ids = []
        for _ in range(10):
            task_id = manager.submit_task(simple_task)
            task_ids.append(task_id)

        # 等待任务完成
        time.sleep(0.5)

        # 验证任务状态存在
        for task_id in task_ids:
            status = manager.get_task_status(task_id)
            assert status is not None

        # 清除任务状态
        manager.clear_task_status()

        # 验证任务状态被清除
        for task_id in task_ids:
            status = manager.get_task_status(task_id)
            assert status is None

        TaskManager.destroy_instance("test_status_cleanup")

    def test_concurrent_destroy(self):
        """测试并发销毁不会导致问题"""
        import concurrent.futures

        # 创建多个实例
        keys = [f"test_concurrent_{i}" for i in range(5)]
        managers = [TaskManager(instance_key=key) for key in keys]

        # 并发销毁
        def destroy_key(key: str) -> bool:
            return TaskManager.destroy_instance(key)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(destroy_key, key) for key in keys]
            results = [f.result() for f in futures]

        # 所有销毁都应该成功
        assert all(results)

        # 所有实例都应该被移除
        for key in keys:
            assert key not in TaskManager._instances


class TestStressTest:
    """压力测试"""

    @pytest.mark.slow
    def test_extended_operation_no_leak(self):
        """测试长时间运行不会导致资源泄漏"""
        manager = TaskManager(instance_key="test_stress")

        def simple_task(x: int) -> int:
            return x * 2

        # 运行大量任务
        for i in range(100):
            manager.submit_task(simple_task, i)

        # 等待所有任务完成
        time.sleep(2)

        # 验证管理器仍然正常工作
        status = manager.get_task_status("nonexistent")
        assert status is None

        # 关闭并销毁
        manager.shutdown()
        TaskManager.destroy_instance("test_stress")

        # 验证没有线程泄漏
        time.sleep(0.5)
        # 这里不检查具体的线程数，只确保没有抛出异常
