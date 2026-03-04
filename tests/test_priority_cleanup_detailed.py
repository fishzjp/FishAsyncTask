"""
优先级队列清理模块测试
"""

import pytest
import time

from fish_async_task.performance.priority_cleanup import TaskStatusWithExpiry


class TestTaskStatusWithExpiry:
    """测试 TaskStatusWithExpiry 类"""

    def test_init_default(self):
        """测试默认初始化"""
        store = TaskStatusWithExpiry()
        assert store.ttl == 300
        assert store.get_task_count() == 0

    def test_init_custom_ttl(self):
        """测试自定义 TTL"""
        store = TaskStatusWithExpiry(ttl=600)
        assert store.ttl == 600

    def test_init_invalid_ttl(self):
        """测试无效 TTL"""
        with pytest.raises(ValueError, match="ttl 必须 >= 1"):
            TaskStatusWithExpiry(ttl=0)

    def test_add_task_with_end_time(self):
        """测试添加带结束时间的任务"""
        store = TaskStatusWithExpiry(ttl=300)
        now = time.time()

        store.add_task("task1", {"status": "completed", "end_time": now})
        assert store.get_task_count() == 1

        result = store.get_task("task1")
        assert result is not None
        assert result["status"] == "completed"

    def test_add_task_without_end_time(self):
        """测试添加不带结束时间的任务"""
        store = TaskStatusWithExpiry(ttl=300)

        store.add_task("task1", {"status": "pending"})
        assert store.get_task_count() == 1
        assert len(store.expiry_heap) == 0  # 没有进入堆

    def test_get_task_not_found(self):
        """测试获取不存在的任务"""
        store = TaskStatusWithExpiry()
        result = store.get_task("nonexistent")
        assert result is None

    def test_cleanup_expired_none(self):
        """测试清理没有过期任务"""
        store = TaskStatusWithExpiry(ttl=300)
        now = time.time()

        store.add_task("task1", {"status": "completed", "end_time": now})
        count = store.cleanup_expired()
        assert count == 0
        assert store.get_task_count() == 1

    def test_cleanup_expired_tasks(self):
        """测试清理过期任务"""
        store = TaskStatusWithExpiry(ttl=1)  # 1秒 TTL
        past_time = time.time() - 2  # 2秒前

        store.add_task("task1", {"status": "completed", "end_time": past_time})
        store.add_task("task2", {"status": "completed", "end_time": past_time})
        store.add_task("task3", {"status": "completed", "end_time": time.time()})  # 未过期

        count = store.cleanup_expired()
        assert count == 2
        assert store.get_task_count() == 1
        assert store.get_task("task1") is None
        assert store.get_task("task2") is None
        assert store.get_task("task3") is not None

    def test_cleanup_expired_with_max(self):
        """测试带最大清理数量的清理"""
        store = TaskStatusWithExpiry(ttl=1)
        past_time = time.time() - 2

        for i in range(10):
            store.add_task(f"task{i}", {"status": "completed", "end_time": past_time})

        count = store.cleanup_expired(max_cleanup=5)
        assert count == 5
        assert store.get_task_count() == 5

    def test_enforce_max_count_within_limit(self):
        """测试强制执行最大数量限制 - 未超限"""
        store = TaskStatusWithExpiry()
        now = time.time()

        for i in range(5):
            store.add_task(f"task{i}", {"status": "completed", "end_time": now})

        count = store.enforce_max_count(10)
        assert count == 0
        assert store.get_task_count() == 5

    def test_enforce_max_count_exceeds_limit(self):
        """测试强制执行最大数量限制 - 超限"""
        store = TaskStatusWithExpiry()
        now = time.time()

        # 添加10个任务
        for i in range(10):
            store.add_task(f"task{i}", {
                "status": "completed",
                "end_time": now,
                "submit_time": now - i  # 不同的提交时间
            })

        count = store.enforce_max_count(5)
        assert count == 5
        assert store.get_task_count() == 5

    def test_enforce_max_count_oldest_first(self):
        """测试强制执行 - 最旧的任务先被删除"""
        store = TaskStatusWithExpiry()
        now = time.time()

        # 添加任务，时间递增
        for i in range(5):
            store.add_task(f"task{i}", {
                "status": "pending",
                "submit_time": now + i  # 最新的时间戳更大
            })

        # 限制为3个，应该删除最旧的2个（task0, task1）
        count = store.enforce_max_count(3)
        assert count == 2
        assert store.get_task_count() == 3
        assert store.get_task("task0") is None
        assert store.get_task("task1") is None
        assert store.get_task("task2") is not None
        assert store.get_task("task3") is not None
        assert store.get_task("task4") is not None

    def test_get_task_count(self):
        """测试获取任务数量"""
        store = TaskStatusWithExpiry()
        assert store.get_task_count() == 0

        now = time.time()
        store.add_task("task1", {"status": "pending", "end_time": now})
        assert store.get_task_count() == 1

        store.add_task("task2", {"status": "pending"})
        assert store.get_task_count() == 2

    def test_get_all_statuses(self):
        """测试获取所有状态"""
        store = TaskStatusWithExpiry()
        now = time.time()

        store.add_task("task1", {"status": "pending", "end_time": now})
        store.add_task("task2", {"status": "running"})

        all_statuses = store.get_all_statuses()
        assert len(all_statuses) == 2
        assert "task1" in all_statuses
        assert "task2" in all_statuses

    def test_cleanup_removes_from_heap(self):
        """测试清理从堆中移除任务"""
        store = TaskStatusWithExpiry(ttl=1)
        past_time = time.time() - 2

        store.add_task("task1", {"status": "completed", "end_time": past_time})

        # 验证任务在堆中
        assert len(store.expiry_heap) > 0

        # 清理后应该从堆中移除
        store.cleanup_expired()
        assert store.get_task("task1") is None

    def test_concurrent_operations(self):
        """测试并发操作"""
        import threading

        store = TaskStatusWithExpiry(ttl=10)
        now = time.time()

        def add_tasks(thread_id):
            for i in range(50):
                store.add_task(f"task{thread_id}_{i}", {
                    "status": "pending",
                    "end_time": now + i
                })

        threads = [threading.Thread(target=add_tasks, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 验证所有任务都已添加
        assert store.get_task_count() == 100

    def test_cleanup_with_gap(self):
        """测试有间隔的清理（部分过期）"""
        store = TaskStatusWithExpiry(ttl=1)
        past = time.time() - 2
        now = time.time()

        # 添加混合过期和未过期的任务
        store.add_task("task1", {"status": "completed", "end_time": past})
        store.add_task("task2", {"status": "completed", "end_time": now})
        store.add_task("task3", {"status": "completed", "end_time": past})

        count = store.cleanup_expired()
        assert count == 2
        assert store.get_task("task2") is not None

    def test_add_task_overwrite(self):
        """测试覆盖已存在的任务"""
        store = TaskStatusWithExpiry()
        now = time.time()

        store.add_task("task1", {"status": "pending", "end_time": now})
        store.add_task("task1", {"status": "completed", "end_time": now})

        result = store.get_task("task1")
        assert result["status"] == "completed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
