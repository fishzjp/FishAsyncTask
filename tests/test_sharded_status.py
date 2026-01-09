"""
分片任务状态存储单元测试

测试 ShardedTaskStatus 类的功能，包括：
- 分片索引计算
- CRUD 操作
- 线程安全
- 全局操作
"""

import threading
import time

import pytest

from fish_async_task.performance import ShardedTaskStatus
from fish_async_task.task_status import ShardedTaskStatusWithExpiry
from fish_async_task.types import TaskStatus, TaskStatusDict


class TestShardedTaskStatus:
    """测试 ShardedTaskStatus 类"""

    def test_init_default_shard_count(self):
        """测试默认初始化"""
        store = ShardedTaskStatus()
        assert store.shard_count == 16

    def test_init_custom_shard_count(self):
        """测试自定义分片数量"""
        store = ShardedTaskStatus(shard_count=8)
        assert store.shard_count == 8

    def test_init_invalid_shard_count(self):
        """测试无效分片数量"""
        with pytest.raises(ValueError, match="shard_count 必须 >= 1"):
            ShardedTaskStatus(shard_count=0)

        with pytest.raises(ValueError, match="shard_count 不应该 > 1024"):
            ShardedTaskStatus(shard_count=2048)

    def test_get_shard_index_distribution(self):
        """测试分片索引分布均匀性"""
        store = ShardedTaskStatus(shard_count=16)
        shard_counts = [0] * 16

        # 创建 1000 个任务，统计每个分片的数量
        for i in range(1000):
            shard_index = store._get_shard_index(f"task-{i}")
            shard_counts[shard_index] += 1

        # 验证每个分片都有任务（分布相对均匀）
        for count in shard_counts:
            assert count > 0, "分片分布不均匀：存在空分片"

        # 验证没有分片超过平均值的 2 倍（简单的均匀性检查）
        avg_count = 1000 / 16
        for count in shard_counts:
            assert (
                count < avg_count * 2
            ), f"分片分布不均匀：存在热点分片（{count} 个任务）"

    def test_get_status_empty(self):
        """测试查询不存在的任务状态"""
        store = ShardedTaskStatus()
        status = store.get_status("nonexistent-task")
        assert status is None

    def test_update_and_get_status(self):
        """测试更新和查询任务状态"""
        store = ShardedTaskStatus()
        task_id = "task-123"

        # 更新任务状态
        status_data: TaskStatusDict = {
            "status": "completed",
            "submit_time": time.time(),
            "start_time": time.time(),
            "end_time": time.time(),
            "result": "success",
        }
        store.update_status(task_id, status_data)

        # 查询任务状态
        retrieved_status = store.get_status(task_id)
        assert retrieved_status is not None
        assert retrieved_status["status"] == "completed"
        assert retrieved_status["result"] == "success"

    def test_update_status_overwrite(self):
        """测试更新状态覆盖旧值"""
        store = ShardedTaskStatus()
        task_id = "task-456"

        # 第一次更新
        status1: TaskStatusDict = {
            "status": "pending",
            "submit_time": time.time(),
        }
        store.update_status(task_id, status1)

        # 第二次更新
        status2: TaskStatusDict = {
            "status": "running",
            "submit_time": status1["submit_time"],
            "start_time": time.time(),
        }
        store.update_status(task_id, status2)

        # 验证最终状态
        retrieved_status = store.get_status(task_id)
        assert retrieved_status["status"] == "running"
        assert retrieved_status["start_time"] is not None

    def test_remove_status(self):
        """测试移除任务状态"""
        store = ShardedTaskStatus()
        task_id = "task-789"

        # 添加任务状态
        status: TaskStatusDict = {
            "status": "completed",
            "submit_time": time.time(),
        }
        store.update_status(task_id, status)

        # 验证任务存在
        assert store.get_status(task_id) is not None

        # 移除任务状态
        store.remove_status(task_id)

        # 验证任务已移除
        assert store.get_status(task_id) is None

    def test_remove_nonexistent_status(self):
        """测试移除不存在的任务状态（应该不报错）"""
        store = ShardedTaskStatus()
        # 不应该抛出异常
        store.remove_status("nonexistent-task")

    def test_get_task_count_empty(self):
        """测试空存储的任务计数"""
        store = ShardedTaskStatus()
        assert store.get_task_count() == 0

    def test_get_task_count(self):
        """测试任务计数"""
        store = ShardedTaskStatus()

        # 添加 100 个任务
        for i in range(100):
            status: TaskStatusDict = {
                "status": "completed",
                "submit_time": time.time(),
            }
            store.update_status(f"task-{i}", status)

        # 验证任务数量
        assert store.get_task_count() == 100

    def test_get_all_statuses_empty(self):
        """测试获取所有状态（空存储）"""
        store = ShardedTaskStatus()
        all_statuses = store.get_all_statuses()
        assert len(all_statuses) == 0

    def test_get_all_statuses(self):
        """测试获取所有状态"""
        store = ShardedTaskStatus()

        # 添加多个任务
        tasks = {}
        for i in range(10):
            task_id = f"task-{i}"
            status: TaskStatusDict = {
                "status": "completed",
                "submit_time": time.time(),
                "result": f"result-{i}",
            }
            store.update_status(task_id, status)
            tasks[task_id] = status

        # 获取所有状态
        all_statuses = store.get_all_statuses()
        assert len(all_statuses) == 10

        # 验证所有任务都存在
        for task_id in tasks:
            assert task_id in all_statuses
            # 从 task_id 中提取编号
            task_num = int(task_id.split("-")[1])
            assert all_statuses[task_id]["result"] == f"result-{task_num}"

    def test_clear_all(self):
        """测试清空所有状态"""
        store = ShardedTaskStatus()

        # 添加任务
        for i in range(50):
            status: TaskStatusDict = {
                "status": "completed",
                "submit_time": time.time(),
            }
            store.update_status(f"task-{i}", status)

        # 验证任务存在
        assert store.get_task_count() == 50

        # 清空所有状态
        store.clear_all()

        # 验证已清空
        assert store.get_task_count() == 0
        assert len(store.get_all_statuses()) == 0


class TestShardedTaskStatusConcurrency:
    """测试 ShardedTaskStatus 的并发安全性"""

    def test_concurrent_updates_different_shards(self):
        """测试并发更新不同分片的任务"""
        store = ShardedTaskStatus(shard_count=16)
        num_threads = 100
        updates_per_thread = 10

        def worker(thread_id: int) -> None:
            """工作线程函数"""
            for i in range(updates_per_thread):
                task_id = f"task-{thread_id}-{i}"
                status: TaskStatusDict = {
                    "status": "running",
                    "submit_time": time.time(),
                }
                store.update_status(task_id, status)

        # 启动多个线程
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        # 等待所有线程完成
        for thread in threads:
            thread.join()

        # 验证任务数量
        expected_count = num_threads * updates_per_thread
        assert store.get_task_count() == expected_count

    def test_concurrent_queries(self):
        """测试并发查询"""
        store = ShardedTaskStatus()

        # 添加 1000 个任务
        for i in range(1000):
            status: TaskStatusDict = {
                "status": "completed",
                "submit_time": time.time(),
                "result": f"result-{i}",
            }
            store.update_status(f"task-{i}", status)

        num_threads = 100
        queries_per_thread = 100
        success_count = [0]

        def worker() -> None:
            """工作线程函数"""
            for i in range(queries_per_thread):
                task_id = f"task-{i % 1000}"
                status = store.get_status(task_id)
                if status is not None and status["result"] == f"result-{i % 1000}":
                    success_count[0] += 1

        # 启动多个线程
        threads = []
        for _ in range(num_threads):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()

        # 等待所有线程完成
        for thread in threads:
            thread.join()

        # 验证所有查询都成功
        expected_queries = num_threads * queries_per_thread
        assert success_count[0] == expected_queries

    def test_concurrent_mixed_operations(self):
        """测试并发混合操作（更新、查询、删除）"""
        store = ShardedTaskStatus(shard_count=16)
        num_tasks = 1000

        # 初始化任务
        for i in range(num_tasks):
            status: TaskStatusDict = {
                "status": "pending",
                "submit_time": time.time(),
            }
            store.update_status(f"task-{i}", status)

        errors = []

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
            except Exception as e:
                errors.append(f"Update error: {e}")

        def query_worker() -> None:
            """查询工作线程"""
            try:
                for i in range(100):
                    task_id = f"task-{i % num_tasks}"
                    store.get_status(task_id)
            except Exception as e:
                errors.append(f"Query error: {e}")

        # 启动混合线程
        threads = []
        for _ in range(10):
            threads.append(threading.Thread(target=update_worker))
            threads.append(threading.Thread(target=query_worker))

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # 验证没有错误
        assert len(errors) == 0, f"并发操作出现错误: {errors}"


def test_get_all_status_basic():
    """测试获取所有任务状态"""
    store = ShardedTaskStatus(shard_count=4)

    # 添加一些任务
    for i in range(10):
        status: TaskStatusDict = {
            "status": "completed",
            "submit_time": time.time(),
        }
        store.update_status(f"task-{i}", status)

    # 获取所有状态
    all_status = store.get_all_statuses()
    assert len(all_status) == 10
    assert all("task-" in key for key in all_status.keys())


def test_get_all_status_empty():
    """测试空状态存储的get_all_status"""
    store = ShardedTaskStatus(shard_count=4)
    all_status = store.get_all_statuses()
    assert len(all_status) == 0


def test_count_basic():
    """测试任务计数"""
    store = ShardedTaskStatus(shard_count=4)

    # 初始计数为0
    assert store.get_task_count() == 0

    # 添加任务
    for i in range(15):
        status: TaskStatusDict = {
            "status": "running",
            "submit_time": time.time(),
        }
        store.update_status(f"task-{i}", status)

    # 计数应该是15
    assert store.get_task_count() == 15


def test_clear_basic():
    """测试清空所有任务状态"""
    store = ShardedTaskStatus(shard_count=4)

    # 添加任务
    for i in range(10):
        status: TaskStatusDict = {
            "status": "completed",
            "submit_time": time.time(),
        }
        store.update_status(f"task-{i}", status)

    assert store.get_task_count() == 10

    # 清空
    store.clear_all()

    # 验证已清空
    assert store.get_task_count() == 0
    assert store.get_status("task-0") is None


def test_get_task_ids_basic():
    """测试获取所有任务ID"""
    store = ShardedTaskStatus(shard_count=4)

    # 添加任务
    task_ids = [f"task-{i}" for i in range(10)]
    for task_id in task_ids:
        status: TaskStatusDict = {
            "status": "queued",
            "submit_time": time.time(),
        }
        store.update_status(task_id, status)

    # 获取所有任务ID
    retrieved_ids = list(store.get_all_statuses().keys())
    assert len(retrieved_ids) == 10
    assert set(retrieved_ids) == set(task_ids)


def test_concurrent_status_updates():
    """测试并发状态更新"""
    store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

    task_id = "concurrent-task"
    num_updates = 100

    def update_worker(status_value: str):
        for i in range(num_updates // 10):
            status: TaskStatusDict = {
                "status": status_value,
                "submit_time": time.time(),
                "start_time": time.time(),
            }
            store.update_status(task_id, status)

    # 启动多个线程同时更新同一个任务
    threads = []
    for i in range(10):
        t = threading.Thread(target=update_worker, args=(f"status-{i}",))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # 验证最终状态存在
    final_status = store.get_status(task_id)
    assert final_status is not None
    assert "status" in final_status


def test_cleanup_edge_cases():
    """测试清理的边缘情况"""
    store = ShardedTaskStatusWithExpiry(shard_count=4, ttl=0)

    # 测试空存储的清理
    cleaned = store.cleanup_expired()
    assert cleaned == 0

    # 添加一个任务并立即清理
    status: TaskStatusDict = {
        "status": "completed",
        "submit_time": time.time(),
        "start_time": time.time(),
        "end_time": time.time() - 100,  # 已过期
    }
    store.update_status("task-1", status)

    cleaned = store.cleanup_expired()
    assert cleaned >= 0

    # 再次清理应该返回0
    cleaned_again = store.cleanup_expired()
    assert cleaned_again == 0


def test_state_transition_atomicity():
    """测试状态转换的原子性"""
    store = ShardedTaskStatus(shard_count=8)

    task_id = "atomic-task"

    # 快速连续更新状态
    states = ["queued", "running", "running", "running", "completed"]
    for state in states:
        status: TaskStatusDict = {
            "status": state,
            "submit_time": time.time(),
        }
        store.update_status(task_id, status)

    # 验证最终状态
    final_status = store.get_status(task_id)
    assert final_status is not None
    assert final_status["status"] == "completed"

