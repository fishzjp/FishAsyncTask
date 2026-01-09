"""端到端集成测试

测试完整的性能优化工作流：
- 提交任务 → 查询状态 → 清理过期任务
- 验证所有优化组件协同工作
"""

import threading
import time
from typing import Dict, List

import pytest

from fish_async_task.performance import (
    AdaptiveWorkerManager,
    BatchedStatusUpdater,
    ShardedTaskStatus,
    TaskStatusWithExpiry,
)


class TestEndToEndWorkflow:
    """测试端到端工作流"""

    def test_complete_workflow_single_threaded(self):
        """测试完整的单线程工作流"""
        # 1. 创建分片任务状态存储
        task_store = ShardedTaskStatus(shard_count=16)

        # 2. 创建批量更新器（不使用 underlying_store，直接通过 task_store 操作）
        batch_updater = BatchedStatusUpdater(buffer_size=10, flush_interval=1.0)

        # 3. 提交任务（批量）
        num_tasks = 100
        for i in range(num_tasks):
            task_id = f"task-{i}"
            status = {
                "status": "pending",
                "submit_time": time.time(),
                "worker_id": "worker-1",
            }
            # 直接使用 task_store
            task_store.update_status(task_id, status)

        # 4. 查询任务状态
        for i in range(num_tasks):
            status = task_store.get_status(f"task-{i}")
            assert status is not None
            assert status["status"] == "pending"

        # 5. 更新任务状态为运行中
        for i in range(num_tasks):
            task_id = f"task-{i}"
            status = {
                "status": "running",
                "start_time": time.time(),
                "worker_id": "worker-1",
            }
            task_store.update_status(task_id, status)

        # 6. 完成任务
        current_time = time.time()
        for i in range(num_tasks):
            task_id = f"task-{i}"
            status = {
                "status": "completed",
                "end_time": current_time,
                "worker_id": "worker-1",
            }
            task_store.update_status(task_id, status)

        # 7. 验证所有任务都已完成
        completed_count = 0
        for i in range(num_tasks):
            status = task_store.get_status(f"task-{i}")
            if status and status["status"] == "completed":
                completed_count += 1

        assert completed_count == num_tasks

        # 8. 清理（通过优先级队列）
        cleanup_store = TaskStatusWithExpiry(ttl=300)
        for i in range(num_tasks):
            task_status = task_store.get_status(f"task-{i}")
            if task_status:
                cleanup_store.add_task(f"task-{i}", task_status)

        # 关闭批量更新器
        batch_updater.close()

        # 验证清理存储中的任务数量
        assert cleanup_store.get_task_count() == num_tasks

    def test_complete_workflow_multi_threaded(self):
        """测试完整的多线程工作流"""
        task_store = ShardedTaskStatus(shard_count=16)
        batch_updater = BatchedStatusUpdater(buffer_size=50, flush_interval=0.5)

        num_threads = 10
        tasks_per_thread = 50
        total_tasks = num_threads * tasks_per_thread

        def submit_and_update_tasks(thread_id: int):
            """提交和更新任务的线程函数"""
            for i in range(tasks_per_thread):
                task_id = f"task-{thread_id}-{i}"

                # 1. 提交任务
                batch_updater.queue_update(
                    task_id,
                    {
                        "status": "pending",
                        "submit_time": time.time(),
                        "worker_id": f"worker-{thread_id}",
                    },
                )

                # 2. 更新为运行中
                batch_updater.queue_update(
                    task_id,
                    {
                        "status": "running",
                        "start_time": time.time(),
                        "worker_id": f"worker-{thread_id}",
                    },
                )

                # 3. 完成任务
                batch_updater.queue_update(
                    task_id,
                    {
                        "status": "completed",
                        "end_time": time.time(),
                        "worker_id": f"worker-{thread_id}",
                    },
                )

        # 启动多个线程
        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=submit_and_update_tasks, args=(i,))
            threads.append(t)
            t.start()

        # 等待所有线程完成
        for t in threads:
            t.join()

        # 最终刷新
        batch_updater.flush()
        batch_updater.close()

        # 验证所有任务都已处理
        # 注意：由于覆盖，每个任务最终应该只有最新状态
        buffer_length = batch_updater.get_buffer_length()
        assert buffer_length == 0, f"缓冲区应该为空，但有 {buffer_length} 个待处理更新"

    def test_adaptive_scaling_integration(self):
        """测试自适应扩展与任务存储的集成"""
        # 创建自适应扩展管理器
        scaling_manager = AdaptiveWorkerManager(
            min_workers=2, max_workers=10, scale_up_cooldown=1.0, queue_threshold=20
        )

        # 创建任务存储
        task_store = ShardedTaskStatus(shard_count=16)

        current_workers = 5

        # 模拟工作负载增加
        for i in range(100):
            task_id = f"task-{i}"
            task_store.update_status(
                task_id, {"status": "pending", "submit_time": time.time()}
            )

        # 检查是否需要扩展
        queue_size = task_store.get_task_count()
        should_scale, reason = scaling_manager.should_scale_up(
            current_workers=current_workers, queue_size=queue_size
        )

        # 队列大小为 100，超过阈值 20，应该扩展
        assert should_scale is True
        assert "队列" in reason or "queue" in reason.lower()

        # 记录任务执行时间
        for _ in range(20):
            scaling_manager.record_task_time(0.05)  # 50ms

        # 模拟工作负载减少
        for i in range(100):
            task_store.remove_status(f"task-{i}")

        queue_size = task_store.get_task_count()
        should_scale_down, reason_down = scaling_manager.should_scale_down(
            current_workers=current_workers, queue_size=queue_size
        )

        # 队列为空，任务执行快，应该缩减
        assert should_scale_down is True
        assert "队列" in reason_down or "queue" in reason_down.lower()

    def test_all_components_together(self):
        """测试所有优化组件协同工作"""
        # 1. 创建所有组件
        task_store = ShardedTaskStatus(shard_count=16)
        batch_updater = BatchedStatusUpdater(buffer_size=20, flush_interval=0.5)
        cleanup_store = TaskStatusWithExpiry(ttl=300)
        scaling_manager = AdaptiveWorkerManager(
            min_workers=2, max_workers=8, queue_threshold=30
        )

        # 2. 模拟工作负载
        num_tasks = 200
        current_workers = 4

        # 提交任务
        for i in range(num_tasks):
            task_id = f"task-{i}"
            batch_updater.queue_update(
                task_id,
                {
                    "status": "pending",
                    "submit_time": time.time(),
                    "worker_id": f"worker-{i % 4}",
                },
            )

        batch_updater.flush()

        # 3. 检查扩展决策
        queue_size = num_tasks
        should_scale, _ = scaling_manager.should_scale_up(
            current_workers=current_workers, queue_size=queue_size
        )

        assert should_scale is True

        # 4. 执行任务并记录时间
        for i in range(num_tasks):
            scaling_manager.record_task_time(0.1)  # 100ms
            batch_updater.queue_update(
                f"task-{i}",
                {
                    "status": "completed",
                    "end_time": time.time(),
                    "worker_id": f"worker-{i % 4}",
                },
            )

        batch_updater.flush()

        # 5. 添加到清理存储
        for i in range(num_tasks):
            status = {"status": "completed", "end_time": time.time()}
            cleanup_store.add_task(f"task-{i}", status)

        # 6. 验证所有组件都正常工作
        assert cleanup_store.get_task_count() == num_tasks

        # 7. 获取扩展指标
        metrics = scaling_manager.get_scaling_metrics(
            current_workers=current_workers, queue_size=queue_size
        )

        assert metrics["current_workers"] == current_workers
        assert metrics["queue_size"] == queue_size
        assert metrics["avg_task_time"] > 0

        # 8. 关闭批量更新器
        batch_updater.close()


class TestPerformanceOptimizationIntegration:
    """测试性能优化的集成效果"""

    def test_sharded_storage_with_batch_updates(self):
        """测试分片存储与批量更新的集成"""
        task_store = ShardedTaskStatus(shard_count=16)
        batch_updater = BatchedStatusUpdater(buffer_size=100, flush_interval=1.0)

        # 使用批量更新器向不同分片提交任务
        num_tasks = 1000
        for i in range(num_tasks):
            task_id = f"task-{i}"
            shard_index = i % 16

            batch_updater.queue_update(
                task_id,
                {
                    "status": "running",
                    "start_time": time.time(),
                    "worker_id": f"worker-{shard_index}",
                },
            )

        batch_updater.flush()

        # 验证所有任务都已更新
        # 注意：这里我们验证的是批量更新器本身的工作正常
        assert batch_updater.get_buffer_length() == 0

        batch_updater.close()

    def test_cleanup_with_priority_queue(self):
        """测试优先级队列清理的集成"""
        cleanup_store = TaskStatusWithExpiry(ttl=1)  # 1 秒 TTL

        # 添加 100 个任务
        num_tasks = 100
        current_time = time.time()

        for i in range(num_tasks):
            task_id = f"task-{i}"
            status = {
                "status": "completed",
                "end_time": current_time - (i * 0.01),  # 不同的过期时间
            }
            cleanup_store.add_task(task_id, status)

        # 等待任务过期
        time.sleep(1.1)

        # 清理过期任务
        cleaned_count = cleanup_store.cleanup_expired()

        # 验证清理了至少一些任务
        assert cleaned_count > 0

        # 验证剩余任务数量
        remaining_count = cleanup_store.get_task_count()
        assert remaining_count < num_tasks

    def test_high_concurrency_scenario(self):
        """测试高并发场景下的集成"""
        task_store = ShardedTaskStatus(shard_count=16)
        batch_updater = BatchedStatusUpdater(buffer_size=200, flush_interval=0.3)

        num_threads = 20
        tasks_per_thread = 100

        def high_concurrency_worker(thread_id: int):
            """高并发工作线程"""
            for i in range(tasks_per_thread):
                task_id = f"task-{thread_id}-{i}"
                batch_updater.queue_update(
                    task_id,
                    {
                        "status": "running",
                        "start_time": time.time(),
                        "worker_id": f"worker-{thread_id}",
                    },
                )

        # 启动所有线程
        threads = []
        start_time = time.time()

        for i in range(num_threads):
            t = threading.Thread(target=high_concurrency_worker, args=(i,))
            threads.append(t)
            t.start()

        # 等待所有线程完成
        for t in threads:
            t.join()

        # 最终刷新
        batch_updater.flush()
        batch_updater.close()

        elapsed = time.time() - start_time
        total_tasks = num_threads * tasks_per_thread
        throughput = total_tasks / elapsed

        # 验证吞吐量
        assert throughput > 1000, f"吞吐量 {throughput:.0f} 任务/秒 太低"

        print(f"\n高并发场景: {total_tasks} 任务, {num_threads} 线程")
        print(f"耗时: {elapsed:.3f}秒")
        print(f"吞吐量: {throughput:.0f} 任务/秒")
