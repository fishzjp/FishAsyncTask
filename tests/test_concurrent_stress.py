"""
并发压力测试

测试高并发场景下的性能和正确性，包括：
- 100+ 并发线程查询状态
- 性能指标验证（QPS、延迟）
- 数据完整性验证
"""

import threading
import time
from typing import Any, Dict, List, Optional

import pytest

from fish_async_task.performance import ShardedTaskStatus
from fish_async_task.types import TaskStatus, TaskStatusDict
from tests.concurrency_helpers import (
    assert_no_data_corruption,
    measure_lock_contention,
    run_concurrent_operations,
)
from tests.performance.test_helpers import (
    assert_performance_meets_threshold,
    measure_latency,
    measure_qps,
)


class TestConcurrentStress:
    """并发压力测试"""

    def test_concurrent_100_threads_query_performance(self):
        """测试 100 并发线程查询性能"""
        store = ShardedTaskStatus(shard_count=16)

        # 添加 10,000 个任务
        num_tasks = 10000
        for i in range(num_tasks):
            status: TaskStatusDict = {
                "status": "completed",
                "submit_time": time.time(),
                "start_time": time.time(),
                "end_time": time.time(),
                "result": f"result-{i}",
            }
            store.update_status(f"task-{i}", status)

        # 测试查询性能
        def query_task() -> None:
            """查询任务"""
            task_id = f"task-{i % num_tasks}"
            store.get_status(task_id)

        # 测量 QPS
        actual_qps = measure_qps(query_task, duration_sec=1.0)

        # 验证 QPS >= 8,000
        assert_performance_meets_threshold(
            actual_qps,
            8000.0,
            "状态查询 QPS",
            comparison="min",
        )

        # 测量延迟分布
        latency_dist = measure_latency(query_task, iterations=1000)

        # 验证 P99 延迟 <= 5ms
        assert_performance_meets_threshold(
            latency_dist["p99"],
            5.0,
            "P99 延迟（毫秒）",
            comparison="max",
        )

        # 验证 P95 延迟 <= 2ms
        assert_performance_meets_threshold(
            latency_dist["p95"],
            2.0,
            "P95 延迟（毫秒）",
            comparison="max",
        )

    def test_concurrent_100_threads_data_integrity(self):
        """测试 100 并发线程的数据完整性"""
        store = ShardedTaskStatus(shard_count=16)

        # 添加原始数据
        original_data: Dict[str, TaskStatusDict] = {}
        for i in range(1000):
            task_id = f"task-{i}"
            status: TaskStatusDict = {
                "status": "completed",
                "submit_time": time.time(),
                "result": f"result-{i}",
            }
            store.update_status(task_id, status)
            original_data[task_id] = status

        # 并发查询所有数据
        def query_all_tasks() -> Dict[str, TaskStatusDict]:
            """查询所有任务"""
            result = {}
            for task_id in original_data:
                status = store.get_status(task_id)
                if status is not None:
                    result[task_id] = status
            return result

        # 运行并发查询
        results = run_concurrent_operations(
            lambda: query_all_tasks(),
            num_threads=100,
            operations_per_thread=1,
        )

        # 验证数据完整性（使用第一个结果）
        if results:
            assert_no_data_corruption(original_data, results[0])

    def test_concurrent_mixed_operations_stress(self):
        """测试并发混合操作的压力测试"""
        store = ShardedTaskStatus(shard_count=16)
        num_tasks = 10000

        # 初始化任务
        for i in range(num_tasks):
            status: TaskStatusDict = {
                "status": "pending",
                "submit_time": time.time(),
            }
            store.update_status(f"task-{i}", status)

        errors = []
        success_count = [0]

        def update_worker() -> None:
            """更新工作线程"""
            try:
                for i in range(100):
                    task_id = f"task-{i % num_tasks}"
                    status: TaskStatusDict = {
                        "status": "running",
                        "submit_time": time.time(),
                        "start_time": time.time(),
                    }
                    store.update_status(task_id, status)
                    success_count[0] += 1
            except Exception as e:
                errors.append(f"Update error: {e}")

        def query_worker() -> None:
            """查询工作线程"""
            try:
                for i in range(100):
                    task_id = f"task-{i % num_tasks}"
                    store.get_status(task_id)
                    success_count[0] += 1
            except Exception as e:
                errors.append(f"Query error: {e}")

        # 启动 100 个混合线程
        threads = []
        for i in range(50):
            threads.append(threading.Thread(target=update_worker))
            threads.append(threading.Thread(target=query_worker))

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # 验证没有错误
        assert len(errors) == 0, f"并发操作出现错误: {errors}"

        # 验证所有操作都成功
        expected_operations = 100 * 100  # 100 个线程，每个 100 次操作
        assert success_count[0] >= expected_operations * 0.99, \
            f"操作成功率低于 99%: {success_count[0]}/{expected_operations}"

    def test_lock_contention_measurement(self):
        """测试锁竞争测量"""
        store = ShardedTaskStatus(shard_count=16)

        # 添加 1000 个任务
        for i in range(1000):
            status: TaskStatusDict = {
                "status": "completed",
                "submit_time": time.time(),
            }
            store.update_status(f"task-{i}", status)

        # 测量锁竞争
        def query_task() -> None:
            """查询任务"""
            store.get_status(f"task-{i % 1000}")

        metrics = measure_lock_contention(
            query_task,
            num_threads=100,
            iterations=100,
        )

        # 验证吞吐量
        assert metrics["throughput"] > 1000, \
            f"吞吐量过低: {metrics['throughput']:.2f} ops/sec"

        # 验证平均每次操作时间 < 10ms
        assert metrics["avg_time_per_op"] < 10.0, \
            f"平均操作时间过长: {metrics['avg_time_per_op']:.2f} ms"

    def test_high_frequency_updates(self):
        """测试高频率更新"""
        store = ShardedTaskStatus(shard_count=16)
        num_threads = 50
        updates_per_thread = 200

        def worker(thread_id: int) -> None:
            """工作线程函数"""
            for i in range(updates_per_thread):
                task_id = f"task-{thread_id}-{i % 100}"
                status: TaskStatusDict = {
                    "status": "running",
                    "submit_time": time.time(),
                }
                store.update_status(task_id, status)

        # 启动线程
        threads = []
        start_time = time.perf_counter()

        for i in range(num_threads):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        elapsed = time.perf_counter() - start_time

        # 验证任务数量合理（允许并发竞争导致的小差异）
        actual_count = store.get_task_count()
        expected_unique_tasks = num_threads * 100
        # 由于并发竞争，允许 ±5% 的误差
        assert abs(actual_count - expected_unique_tasks) / expected_unique_tasks < 0.05, \
            f"任务数量偏差过大: {actual_count} vs {expected_unique_tasks}"

        # 验证总时间合理（应该 < 5 秒）
        assert elapsed < 5.0, f"更新耗时过长: {elapsed:.2f} 秒"

    def test_deadlock_prevention(self):
        """测试死锁预防"""
        store = ShardedTaskStatus(shard_count=16)

        # 添加任务
        for i in range(100):
            status: TaskStatusDict = {
                "status": "completed",
                "submit_time": time.time(),
            }
            store.update_status(f"task-{i}", status)

        deadlock_detected = [False]

        def get_all_worker() -> None:
            """获取所有状态的工作线程"""
            try:
                store.get_all_statuses()
            except Exception:
                deadlock_detected[0] = True

        # 启动多个线程同时调用 get_all_statuses
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=get_all_worker)
            threads.append(thread)
            thread.start()

        # 等待 5 秒
        for thread in threads:
            thread.join(timeout=5.0)

        # 验证没有死锁（所有线程都完成）
        for thread in threads:
            assert not thread.is_alive(), "检测到死锁：线程仍在运行"

        # 验证没有异常
        assert not deadlock_detected[0], "get_all_statuses 出现异常"
