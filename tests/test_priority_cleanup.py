"""
优先级队列清理单元测试

测试 TaskStatusWithExpiry 类的功能，包括：
- 添加任务到优先级队列
- 清理过期任务
- 强制执行最大数量限制
- 线程安全
"""

import threading
import time

import pytest

from fish_async_task.performance.priority_cleanup import TaskStatusWithExpiry
from fish_async_task.types import TaskStatusDict


class TestTaskStatusWithExpiry:
    """测试 TaskStatusWithExpiry 类"""

    def test_init_default_ttl(self):
        """测试默认初始化"""
        store = TaskStatusWithExpiry()
        assert store.ttl == 300  # 默认 5 分钟

    def test_init_custom_ttl(self):
        """测试自定义 TTL"""
        store = TaskStatusWithExpiry(ttl=600)
        assert store.ttl == 600

    def test_add_task_with_end_time(self):
        """测试添加带 end_time 的任务"""
        store = TaskStatusWithExpiry(ttl=300)
        task_id = "task-123"
        end_time = time.time()

        status: TaskStatusDict = {
            "task_id": task_id,
            "status": "completed",
            "submit_time": time.time(),
            "end_time": end_time,
            "result": "success",
        }

        store.add_task(task_id, status)

        # 验证任务被添加
        assert store.get_task_count() == 1
        retrieved = store.get_task(task_id)
        assert retrieved is not None
        assert retrieved["status"] == "completed"

    def test_add_task_without_end_time(self):
        """测试添加不带 end_time 的任务（应该不加入优先级队列）"""
        store = TaskStatusWithExpiry(ttl=300)
        task_id = "task-456"

        status: TaskStatusDict = {
            "task_id": task_id,
            "status": "running",
            "submit_time": time.time(),
            "start_time": time.time(),
        }

        store.add_task(task_id, status)

        # 任务被添加但不在优先级队列中
        assert store.get_task_count() == 1

    def test_cleanup_expired_tasks(self):
        """测试清理过期任务"""
        store = TaskStatusWithExpiry(ttl=1)  # 1 秒 TTL
        current_time = time.time()

        # 添加 10 个任务，其中 5 个已过期
        for i in range(10):
            end_time = current_time - 2 if i < 5 else current_time + 10
            status: TaskStatusDict = {
                "task_id": f"task-{i}",
                "status": "completed",
                "submit_time": current_time,
                "end_time": end_time,
            }
            store.add_task(f"task-{i}", status)

        assert store.get_task_count() == 10

        # 清理过期任务
        cleaned_count = store.cleanup_expired()

        # 应该清理 5 个过期任务
        assert cleaned_count == 5
        assert store.get_task_count() == 5

    def test_cleanup_expired_with_max_cleanup(self):
        """测试使用 max_cleanup 参数的增量清理"""
        store = TaskStatusWithExpiry(ttl=1)
        current_time = time.time()

        # 添加 100 个过期任务
        for i in range(100):
            status: TaskStatusDict = {
                "task_id": f"task-{i}",
                "status": "completed",
                "submit_time": current_time,
                "end_time": current_time - 10,  # 已过期
            }
            store.add_task(f"task-{i}", status)

        # 每次最多清理 10 个
        total_cleaned = 0
        iteration = 0
        while True:
            cleaned = store.cleanup_expired(max_cleanup=10)
            total_cleaned += cleaned
            iteration += 1
            if cleaned == 0 or iteration > 20:
                break

        assert total_cleaned == 100
        assert store.get_task_count() == 0

    def test_cleanup_no_expired_tasks(self):
        """测试清理时没有过期任务"""
        store = TaskStatusWithExpiry(ttl=300)
        current_time = time.time()

        # 添加未过期的任务
        for i in range(10):
            status: TaskStatusDict = {
                "task_id": f"task-{i}",
                "status": "completed",
                "submit_time": current_time,
                "end_time": current_time + 100,  # 未过期
            }
            store.add_task(f"task-{i}", status)

        # 清理过期任务
        cleaned_count = store.cleanup_expired()

        # 不应该清理任何任务
        assert cleaned_count == 0
        assert store.get_task_count() == 10

    def test_enforce_max_count(self):
        """测试强制执行最大数量限制"""
        store = TaskStatusWithExpiry(ttl=300)
        current_time = time.time()

        # 添加 20 个任务
        for i in range(20):
            status: TaskStatusDict = {
                "task_id": f"task-{i}",
                "status": "completed",
                "submit_time": current_time - (20 - i),  # 不同的提交时间
                "end_time": current_time,
            }
            store.add_task(f"task-{i}", status)

        assert store.get_task_count() == 20

        # 强制执行最大数量限制为 10
        removed_count = store.enforce_max_count(max_count=10)

        # 应该删除最旧的 10 个任务
        assert removed_count == 10
        assert store.get_task_count() == 10

        # 验证保留的是最新的任务（task-10 到 task-19）
        all_statuses = store.get_all_statuses()
        task_ids = list(all_statuses.keys())
        assert "task-0" not in task_ids  # 最旧的被删除
        assert "task-19" in task_ids  # 最新的被保留

    def test_enforce_max_count_already_under_limit(self):
        """测试任务数量已经低于限制时"""
        store = TaskStatusWithExpiry(ttl=300)
        current_time = time.time()

        # 添加 5 个任务
        for i in range(5):
            status: TaskStatusDict = {
                "task_id": f"task-{i}",
                "status": "completed",
                "submit_time": current_time,
                "end_time": current_time,
            }
            store.add_task(f"task-{i}", status)

        # 强制执行最大数量限制为 10
        removed_count = store.enforce_max_count(max_count=10)

        # 不应该删除任何任务
        assert removed_count == 0
        assert store.get_task_count() == 5

    def test_get_task_count(self):
        """测试获取任务数量"""
        store = TaskStatusWithExpiry(ttl=300)

        # 初始为空
        assert store.get_task_count() == 0

        # 添加任务
        for i in range(100):
            status: TaskStatusDict = {
                "task_id": f"task-{i}",
                "status": "completed",
                "submit_time": time.time(),
                "end_time": time.time(),
            }
            store.add_task(f"task-{i}", status)

        # 验证数量
        assert store.get_task_count() == 100

    def test_get_all_statuses(self):
        """测试获取所有状态"""
        store = TaskStatusWithExpiry(ttl=300)
        current_time = time.time()

        # 添加任务
        tasks = {}
        for i in range(10):
            task_id = f"task-{i}"
            status: TaskStatusDict = {
                "task_id": task_id,
                "status": "completed",
                "submit_time": current_time,
                "end_time": current_time,
                "result": f"result-{i}",
            }
            store.add_task(task_id, status)
            tasks[task_id] = status

        # 获取所有状态
        all_statuses = store.get_all_statuses()

        assert len(all_statuses) == 10
        for task_id in tasks:
            assert task_id in all_statuses


class TestTaskStatusWithExpiryConcurrency:
    """测试 TaskStatusWithExpiry 的并发安全性"""

    def test_concurrent_add_and_cleanup(self):
        """测试并发添加和清理"""
        store = TaskStatusWithExpiry(ttl=1)
        num_threads = 50
        tasks_per_thread = 20

        errors = []

        def worker(thread_id: int) -> None:
            """工作线程函数"""
            try:
                for i in range(tasks_per_thread):
                    task_id = f"task-{thread_id}-{i}"
                    current_time = time.time()
                    status: TaskStatusDict = {
                        "task_id": task_id,
                        "status": "completed",
                        "submit_time": current_time - 10,  # 已过期
                        "end_time": current_time - 10,
                    }
                    store.add_task(task_id, status)

                # 定期清理
                if thread_id % 10 == 0:  # 每 10 个线程清理一次
                    store.cleanup_expired(max_cleanup=50)

            except Exception as e:
                errors.append(str(e))

        # 启动线程
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # 验证没有错误
        assert len(errors) == 0, f"并发操作出现错误: {errors}"

        # 最终清理所有
        final_cleaned = store.cleanup_expired()
        assert final_cleaned >= 0

    def test_concurrent_cleanup_and_query(self):
        """测试并发清理和查询"""
        store = TaskStatusWithExpiry(ttl=300)
        current_time = time.time()

        # 添加 1000 个任务
        for i in range(1000):
            status: TaskStatusDict = {
                "task_id": f"task-{i}",
                "status": "completed",
                "submit_time": current_time,
                "end_time": current_time,
            }
            store.add_task(f"task-{i}", status)

        errors = []

        def cleanup_worker() -> None:
            """清理工作线程"""
            try:
                for _ in range(10):
                    store.cleanup_expired(max_cleanup=100)
            except Exception as e:
                errors.append(f"Cleanup error: {e}")

        def query_worker() -> None:
            """查询工作线程"""
            try:
                for i in range(100):
                    task_id = f"task-{i % 1000}"
                    store.get_task(task_id)
            except Exception as e:
                errors.append(f"Query error: {e}")

        # 启动混合线程
        threads = []
        for _ in range(5):
            threads.append(threading.Thread(target=cleanup_worker))
            threads.append(threading.Thread(target=query_worker))

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # 验证没有错误
        assert len(errors) == 0, f"并发操作出现错误: {errors}"

        # 验证任务数量仍然正确
        assert store.get_task_count() == 1000
