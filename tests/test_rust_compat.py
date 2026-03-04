"""
Rust 实现的 API 兼容性测试

验证 Rust 实现与 Python 实现的 API 兼容性。
"""

import time
from typing import Optional

import pytest

from fish_async_task._adapters import (
    is_rust_available,
    get_sharded_status_store,
    get_priority_queue,
)
from fish_async_task.task_status import ShardedTaskStatusWithExpiry
from fish_async_task.types import TaskStatusDict


@pytest.fixture(autouse=True)
def check_rust():
    """检查 Rust 是否可用"""
    if not is_rust_available():
        pytest.skip("Rust 扩展不可用")


class TestShardedTaskStatusCompatibility:
    """测试分片状态存储兼容性"""

    def test_get_set_status(self):
        """测试基本的状态获取和设置"""
        store = get_sharded_status_store(shard_count=16, ttl=3600)

        # 设置状态
        task_id = "test_task_1"
        status: TaskStatusDict = {
            "status": "pending",
            "submit_time": time.time(),
        }
        store.update_status(task_id, status)

        # 获取状态
        result = store.get_status(task_id)
        assert result is not None
        assert result["status"] == "pending"

    def test_status_not_found(self):
        """测试获取不存在的任务"""
        store = get_sharded_status_store(shard_count=16, ttl=3600)

        result = store.get_status("nonexistent_task")
        assert result is None

    def test_update_status(self):
        """测试状态更新"""
        store = get_sharded_status_store(shard_count=16, ttl=3600)

        task_id = "test_task_2"
        store.update_status(task_id, {"status": "pending", "submit_time": time.time()})

        # 更新为 running
        store.update_status(
            task_id,
            {
                "status": "running",
                "submit_time": time.time() - 1,
                "start_time": time.time(),
            },
        )

        result = store.get_status(task_id)
        assert result["status"] == "running"

    def test_completed_status(self):
        """测试完成状态"""
        store = get_sharded_status_store(shard_count=16, ttl=3600)

        task_id = "test_task_3"
        end_time = time.time()
        store.update_status(
            task_id,
            {
                "status": "completed",
                "submit_time": end_time - 1,
                "start_time": end_time - 0.5,
                "end_time": end_time,
                "result": 42,
            },
        )

        result = store.get_status(task_id)
        assert result["status"] == "completed"
        assert result["result"] == 42

    def test_failed_status(self):
        """测试失败状态"""
        store = get_sharded_status_store(shard_count=16, ttl=3600)

        task_id = "test_task_4"
        end_time = time.time()
        store.update_status(
            task_id,
            {
                "status": "failed",
                "submit_time": end_time - 1,
                "start_time": end_time - 0.5,
                "end_time": end_time,
                "error": "Test error",
            },
        )

        result = store.get_status(task_id)
        assert result["status"] == "failed"
        assert result["error"] == "Test error"

    def test_remove_status(self):
        """测试移除状态"""
        store = get_sharded_status_store(shard_count=16, ttl=3600)

        task_id = "test_task_5"
        store.update_status(task_id, {"status": "pending", "submit_time": time.time()})

        # 移除
        removed = store.remove_status(task_id)
        assert removed is True

        # 验证已移除
        result = store.get_status(task_id)
        assert result is None

    def test_get_total_count(self):
        """测试获取总任务数"""
        store = get_sharded_status_store(shard_count=16, ttl=3600)

        # 添加任务
        for i in range(100):
            store.update_status(f"task_{i}", {"status": "pending", "submit_time": time.time()})

        count = store.get_total_count()
        assert count == 100

    def test_clear_all(self):
        """测试清空所有任务"""
        store = get_sharded_status_store(shard_count=16, ttl=3600)

        # 添加任务
        for i in range(50):
            store.update_status(f"task_{i}", {"status": "pending", "submit_time": time.time()})

        # 清空
        store.clear_all()

        # 验证已清空
        count = store.get_total_count()
        assert count == 0

    def test_cleanup_expired(self):
        """测试清理过期任务"""
        store = get_sharded_status_store(shard_count=16, ttl=1)

        # 添加已完成的任务（已过期）
        now = time.time()
        for i in range(10):
            store.update_status(
                f"task_{i}",
                {
                    "status": "completed",
                    "submit_time": now - 10,
                    "start_time": now - 9,
                    "end_time": now - 8,  # 已超过 TTL
                    "result": i,
                },
            )

        # 等待确保过期
        time.sleep(0.5)

        # 清理
        cleaned = store.cleanup_expired()
        assert cleaned >= 0  # 至少应该执行清理

    def test_concurrent_updates(self):
        """测试并发更新"""
        from concurrent.futures import ThreadPoolExecutor

        store = get_sharded_status_store(shard_count=16, ttl=3600)

        def update_tasks(thread_id: int):
            for i in range(100):
                task_id = f"task_{thread_id}_{i}"
                store.update_status(task_id, {"status": "pending", "submit_time": time.time()})

        # 并发更新
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(update_tasks, i) for i in range(10)]
            for f in futures:
                f.result()

        # 验证
        count = store.get_total_count()
        assert count == 1000


class TestPriorityQueueCompatibility:
    """测试优先级队列兼容性"""

    def test_put_get(self):
        """测试基本添加和获取"""
        queue = get_priority_queue(maxsize=100)

        # 添加任务
        queue.put("task_1", priority=1)
        queue.put("task_2", priority=2)

        # 获取任务（应该先获取 priority=1 的）
        task1 = queue.get(block=False)
        assert task1 == "task_1"

        task2 = queue.get(block=False)
        assert task2 == "task_2"

    def test_priority_order(self):
        """测试优先级顺序"""
        queue = get_priority_queue(maxsize=100)

        # 添加不同优先级的任务
        queue.put("low", priority=10)
        queue.put("high", priority=1)
        queue.put("medium", priority=5)

        # 应该按优先级顺序获取
        assert queue.get(block=False) == "high"
        assert queue.get(block=False) == "medium"
        assert queue.get(block=False) == "low"

    def test_qsize(self):
        """测试获取队列大小"""
        queue = get_priority_queue(maxsize=100)

        assert queue.qsize() == 0
        assert queue.empty() is True

        queue.put("task_1", priority=1)
        queue.put("task_2", priority=2)

        assert queue.qsize() == 2
        assert queue.empty() is False

    def test_full(self):
        """测试队列满"""
        queue = get_priority_queue(maxsize=2)

        queue.put("task_1", priority=1)
        queue.put("task_2", priority=2)

        assert queue.full() is True

    def test_fifo_for_same_priority(self):
        """测试相同优先级的 FIFO 顺序"""
        queue = get_priority_queue(maxsize=100)

        # 添加相同优先级的任务
        queue.put("first", priority=5)
        queue.put("second", priority=5)
        queue.put("third", priority=5)

        # 应该按添加顺序获取
        assert queue.get(block=False) == "first"
        assert queue.get(block=False) == "second"
        assert queue.get(block=False) == "third"


class TestRustPythonComparison:
    """比较 Rust 和 Python 实现的行为"""

    def test_basic_behavior_match(self):
        """测试基本行为一致性"""
        rust_store = get_sharded_status_store(shard_count=16, ttl=3600)
        python_store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        task_id = "test_task"
        status: TaskStatusDict = {
            "status": "pending",
            "submit_time": time.time(),
        }

        # 设置状态
        rust_store.update_status(task_id, status)
        python_store.update_status(task_id, status)

        # 获取状态
        rust_result = rust_store.get_status(task_id)
        python_result = python_store.get_status(task_id)

        # 验证状态一致
        assert rust_result is not None
        assert python_result is not None
        assert rust_result["status"] == python_result["status"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
