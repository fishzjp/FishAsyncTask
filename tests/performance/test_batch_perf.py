"""批量状态更新性能基准测试

测试 BatchedStatusUpdater 的吞吐量性能，验证是否达到 5,000+ 任务/秒的目标。
"""

import time
from typing import Dict

import pytest

from fish_async_task.performance.batch_updater import BatchedStatusUpdater
from fish_async_task.types import TaskStatusDict


class TestBatchThroughputBenchmark:
    """测试批量状态更新的吞吐量性能"""

    def test_single_thread_throughput(self):
        """测试单线程吞吐量

        目标：5,000+ 任务/秒
        """
        store = {}
        updater = BatchedStatusUpdater(
            buffer_size=100,
            flush_interval=1.0,
            underlying_store=store
        )

        num_tasks = 5000
        start_time = time.time()

        # 添加任务
        for i in range(num_tasks):
            updater.queue_update(f"task-{i}", {"status": "running", "progress": i / num_tasks})

        # 最终刷新
        updater.flush()

        elapsed = time.time() - start_time
        throughput = num_tasks / elapsed

        print(f"\n=== 单线程吞吐量测试 ===")
        print(f"任务数量: {num_tasks}")
        print(f"耗时: {elapsed:.3f}秒")
        print(f"吞吐量: {throughput:.0f} 任务/秒")

        # 验证所有任务都已写入
        assert len(store) == num_tasks

        # 验证吞吐量达到目标（5,000+ 任务/秒）
        assert throughput >= 5000, f"吞吐量 {throughput:.0f} 任务/秒 未达到目标 5,000 任务/秒"

    def test_multi_thread_throughput(self):
        """测试多线程吞吐量

        目标：在 10 个线程下，总体吞吐量 10,000+ 任务/秒
        """
        store = {}
        updater = BatchedStatusUpdater(
            buffer_size=100,
            flush_interval=1.0,
            underlying_store=store
        )

        num_threads = 10
        tasks_per_thread = 500
        total_tasks = num_threads * tasks_per_thread

        import threading

        def batch_updates(thread_id: int):
            for i in range(tasks_per_thread):
                task_id = f"task-{thread_id}-{i}"
                updater.queue_update(task_id, {"status": "running", "thread": thread_id})

        start_time = time.time()

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=batch_updates, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # 最终刷新
        updater.flush()

        elapsed = time.time() - start_time
        throughput = total_tasks / elapsed

        print(f"\n=== 多线程吞吐量测试 ===")
        print(f"线程数量: {num_threads}")
        print(f"每线程任务数: {tasks_per_thread}")
        print(f"总任务数: {total_tasks}")
        print(f"耗时: {elapsed:.3f}秒")
        print(f"吞吐量: {throughput:.0f} 任务/秒")

        # 验证所有任务都已写入
        assert len(store) == total_tasks

        # 验证吞吐量达到目标（10,000+ 任务/秒）
        assert throughput >= 10000, f"吞吐量 {throughput:.0f} 任务/秒 未达到目标 10,000 任务/秒"

    def test_buffer_size_impact(self):
        """测试不同缓冲区大小对性能的影响"""
        num_tasks = 5000

        buffer_sizes = [10, 50, 100, 500, 1000]
        results = []

        for buffer_size in buffer_sizes:
            store = {}
            updater = BatchedStatusUpdater(
                buffer_size=buffer_size,
                flush_interval=10.0,  # 禁用时间触发
                underlying_store=store
            )

            start_time = time.time()

            for i in range(num_tasks):
                updater.queue_update(f"task-{i}", {"status": "running"})

            updater.flush()

            elapsed = time.time() - start_time
            throughput = num_tasks / elapsed

            results.append((buffer_size, elapsed, throughput))

        print(f"\n=== 缓冲区大小对性能的影响 ===")
        print(f"任务数量: {num_tasks}")
        print(f"{'缓冲区大小':<12} {'耗时(秒)':<12} {'吞吐量(任务/秒)':<18}")
        print("-" * 45)
        for buffer_size, elapsed, throughput in results:
            print(f"{buffer_size:<12} {elapsed:<12.3f} {throughput:<18.0f}")

        # 验证所有测试都达到最低吞吐量要求
        for buffer_size, elapsed, throughput in results:
            assert throughput >= 5000, f"缓冲区大小 {buffer_size} 时，吞吐量 {throughput:.0f} 任务/秒 未达到目标"

    def test_flush_interval_impact(self):
        """测试不同刷新间隔对性能的影响"""
        num_tasks = 5000

        flush_intervals = [0.1, 0.5, 1.0, 2.0]
        results = []

        for flush_interval in flush_intervals:
            store = {}
            updater = BatchedStatusUpdater(
                buffer_size=10000,  # 大缓冲区，避免大小触发
                flush_interval=flush_interval,
                underlying_store=store
            )

            start_time = time.time()

            for i in range(num_tasks):
                updater.queue_update(f"task-{i}", {"status": "running"})
                time.sleep(0.00001)  # 10 微秒延迟，模拟真实场景

            updater.flush()

            elapsed = time.time() - start_time
            throughput = num_tasks / elapsed

            results.append((flush_interval, elapsed, throughput))

        print(f"\n=== 刷新间隔对性能的影响 ===")
        print(f"任务数量: {num_tasks}")
        print(f"{'刷新间隔(秒)':<15} {'耗时(秒)':<12} {'吞吐量(任务/秒)':<18}")
        print("-" * 48)
        for flush_interval, elapsed, throughput in results:
            print(f"{flush_interval:<15.1f} {elapsed:<12.3f} {throughput:<18.0f}")

    def test_batch_vs_individual_updates(self):
        """对比批量更新与单独更新的性能"""
        num_tasks = 5000

        # 测试批量更新性能
        batch_store = {}
        batch_updater = BatchedStatusUpdater(
            buffer_size=100,
            flush_interval=10.0,
            underlying_store=batch_store
        )

        start_time = time.time()
        for i in range(num_tasks):
            batch_updater.queue_update(f"task-{i}", {"status": "running"})
        batch_updater.flush()
        batch_elapsed = time.time() - start_time
        batch_throughput = num_tasks / batch_elapsed

        # 测试单独更新性能（模拟）
        individual_store = {}
        start_time = time.time()
        for i in range(num_tasks):
            individual_store[f"task-{i}"] = {"status": "running"}
        individual_elapsed = time.time() - start_time
        individual_throughput = num_tasks / individual_elapsed

        speedup = batch_throughput / individual_throughput

        print(f"\n=== 批量更新 vs 单独更新性能对比 ===")
        print(f"任务数量: {num_tasks}")
        print(f"\n批量更新:")
        print(f"  耗时: {batch_elapsed:.3f}秒")
        print(f"  吞吐量: {batch_throughput:.0f} 任务/秒")
        print(f"\n单独更新:")
        print(f"  耗时: {individual_elapsed:.3f}秒")
        print(f"  吞吐量: {individual_throughput:.0f} 任务/秒")
        print(f"\n性能提升: {speedup:.2f}x")

        # 验证批量更新性能合理
        assert batch_throughput >= 5000, f"批量更新吞吐量 {batch_throughput:.0f} 任务/秒 未达到目标"

    def test_high_frequency_scenario(self):
        """测试高频提交场景（模拟真实工作负载）"""
        store = {}
        updater = BatchedStatusUpdater(
            buffer_size=100,
            flush_interval=0.5,
            underlying_store=store
        )

        num_threads = 20
        tasks_per_thread = 250
        total_tasks = num_threads * tasks_per_thread

        import random
        import threading

        def high_frequency_submissions(thread_id: int):
            for i in range(tasks_per_thread):
                task_id = f"task-{thread_id}-{i}"
                status = {
                    "status": random.choice(["pending", "running", "completed"]),
                    "progress": random.random(),
                    "thread": thread_id
                }
                updater.queue_update(task_id, status)
                # 模拟真实场景中的微小延迟
                time.sleep(0.0001)  # 100 微秒

        start_time = time.time()

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=high_frequency_submissions, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        updater.flush()

        elapsed = time.time() - start_time
        throughput = total_tasks / elapsed

        print(f"\n=== 高频提交场景测试 ===")
        print(f"线程数量: {num_threads}")
        print(f"每线程任务数: {tasks_per_thread}")
        print(f"总任务数: {total_tasks}")
        print(f"耗时: {elapsed:.3f}秒")
        print(f"吞吐量: {throughput:.0f} 任务/秒")

        # 验证所有任务都已写入
        assert len(store) == total_tasks

        # 验证吞吐量达到目标（5,000+ 任务/秒）
        assert throughput >= 5000, f"吞吐量 {throughput:.0f} 任务/秒 未达到目标 5,000 任务/秒"
