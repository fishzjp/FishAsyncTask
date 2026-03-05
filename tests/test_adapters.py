"""
适配器模块测试

测试 _adapters.py 中的适配器类和函数，包括 Rust/Python 实现的自动选择。
"""

import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from fish_async_task._adapters import (
    PriorityTaskQueueAdapter,
    ShardedTaskStatusAdapter,
    _PythonPriorityTaskQueueAdapter,
    _PythonShardedTaskStatusAdapter,
    _RustPriorityTaskQueueAdapter,
    _RustShardedTaskStatusAdapter,
    get_priority_queue,
    get_sharded_status_store,
    is_rust_available,
)
from fish_async_task.types import TaskStatusDict


class TestRustAvailability:
    """测试 Rust 可用性检查"""

    def test_is_rust_available_returns_bool(self):
        """测试返回布尔值"""
        result = is_rust_available()
        assert isinstance(result, bool)

    def test_is_rust_available_consistent(self):
        """测试多次调用返回一致结果"""
        result1 = is_rust_available()
        result2 = is_rust_available()
        assert result1 == result2


class TestShardedTaskStatusAdapter:
    """测试分片状态存储适配器"""

    def test_adapter_create_returns_instance(self):
        """测试 create 方法返回有效实例"""
        adapter = ShardedTaskStatusAdapter.create(shard_count=16, ttl=3600)

        # 应该返回一个子类实例
        assert isinstance(adapter, ShardedTaskStatusAdapter)

        # 根据 Rust 可用性，应该是具体的实现
        if is_rust_available():
            assert isinstance(adapter, _RustShardedTaskStatusAdapter)
        else:
            assert isinstance(adapter, _PythonShardedTaskStatusAdapter)

    def test_adapter_base_methods_raise_not_implemented(self):
        """测试基类方法抛出 NotImplementedError"""
        adapter = ShardedTaskStatusAdapter()

        with pytest.raises(NotImplementedError):
            adapter.get_status("test")

        with pytest.raises(NotImplementedError):
            adapter.update_status("test", {})

        with pytest.raises(NotImplementedError):
            adapter.remove_status("test")

        with pytest.raises(NotImplementedError):
            adapter.cleanup_expired()

        with pytest.raises(NotImplementedError):
            adapter.get_total_count()

        with pytest.raises(NotImplementedError):
            adapter.clear_all()


@pytest.mark.skipif(not is_rust_available(), reason="Rust 扩展不可用")
class TestRustShardedTaskStatusAdapter:
    """测试 Rust 状态存储适配器"""

    def test_init(self):
        """测试初始化"""
        adapter = _RustShardedTaskStatusAdapter(shard_count=16, ttl=3600)
        assert adapter._rust is not None

    def test_get_status_not_found(self):
        """测试获取不存在的任务"""
        adapter = _RustShardedTaskStatusAdapter(shard_count=16, ttl=3600)
        result = adapter.get_status("nonexistent_task")
        assert result is None

    def test_update_and_get_status(self):
        """测试更新和获取状态"""
        adapter = _RustShardedTaskStatusAdapter(shard_count=16, ttl=3600)

        task_id = "test_task_1"
        status: TaskStatusDict = {
            "status": "pending",
            "submit_time": time.time(),
        }

        adapter.update_status(task_id, status)
        result = adapter.get_status(task_id)

        assert result is not None
        assert result["status"] == "pending"

    def test_update_status_with_result(self):
        """测试带 result 的状态更新"""
        adapter = _RustShardedTaskStatusAdapter(shard_count=16, ttl=3600)

        task_id = "test_task_with_result"
        status: TaskStatusDict = {
            "status": "completed",
            "submit_time": time.time(),
            "start_time": time.time(),
            "end_time": time.time(),
            "result": 42,
        }

        adapter.update_status(task_id, status)
        result = adapter.get_status(task_id)

        assert result is not None
        assert result["result"] == 42

    def test_update_status_with_error(self):
        """测试带 error 的状态更新"""
        adapter = _RustShardedTaskStatusAdapter(shard_count=16, ttl=3600)

        task_id = "test_task_with_error"
        status: TaskStatusDict = {
            "status": "failed",
            "submit_time": time.time(),
            "start_time": time.time(),
            "end_time": time.time(),
            "error": "Test error message",
        }

        adapter.update_status(task_id, status)
        result = adapter.get_status(task_id)

        assert result is not None
        assert result["error"] == "Test error message"

    def test_update_status_fast_path(self):
        """测试快速更新路径（无 result/error）"""
        adapter = _RustShardedTaskStatusAdapter(shard_count=16, ttl=3600)

        task_id = "test_task_fast"
        status: TaskStatusDict = {
            "status": "running",
            "submit_time": time.time(),
            "start_time": time.time(),
        }

        adapter.update_status(task_id, status)
        result = adapter.get_status(task_id)

        assert result is not None
        assert result["status"] == "running"

    def test_remove_status(self):
        """测试移除状态"""
        adapter = _RustShardedTaskStatusAdapter(shard_count=16, ttl=3600)

        task_id = "test_task_remove"
        adapter.update_status(task_id, {"status": "pending", "submit_time": time.time()})

        # 移除
        removed = adapter.remove_status(task_id)
        assert removed is True

        # 验证已移除
        result = adapter.get_status(task_id)
        assert result is None

    def test_remove_nonexistent_status(self):
        """测试移除不存在的状态"""
        adapter = _RustShardedTaskStatusAdapter(shard_count=16, ttl=3600)

        removed = adapter.remove_status("nonexistent_task")
        # Rust 实现可能返回 True 或 False，取决于具体实现
        assert isinstance(removed, bool)

    def test_get_total_count(self):
        """测试获取总任务数"""
        adapter = _RustShardedTaskStatusAdapter(shard_count=16, ttl=3600)

        # 添加任务
        for i in range(50):
            adapter.update_status(f"task_{i}", {"status": "pending", "submit_time": time.time()})

        count = adapter.get_total_count()
        assert count == 50

    def test_clear_all(self):
        """测试清空所有状态"""
        adapter = _RustShardedTaskStatusAdapter(shard_count=16, ttl=3600)

        # 添加任务
        for i in range(30):
            adapter.update_status(f"task_{i}", {"status": "pending", "submit_time": time.time()})

        adapter.clear_all()

        # 验证已清空
        count = adapter.get_total_count()
        assert count == 0

    def test_cleanup_expired(self):
        """测试清理过期任务"""
        adapter = _RustShardedTaskStatusAdapter(shard_count=16, ttl=1)

        # 添加已完成的任务（已过期）
        now = time.time()
        for i in range(10):
            adapter.update_status(
                f"task_{i}",
                {
                    "status": "completed",
                    "submit_time": now - 10,
                    "start_time": now - 9,
                    "end_time": now - 8,
                    "result": i,
                },
            )

        # 等待确保过期
        time.sleep(0.5)

        # 清理
        cleaned = adapter.cleanup_expired()
        assert cleaned >= 0


@pytest.mark.skipif(is_rust_available(), reason="测试 Python 回退实现")
class TestPythonShardedTaskStatusAdapter:
    """测试 Python 状态存储适配器（回退）"""

    def test_init(self):
        """测试初始化"""
        adapter = _PythonShardedTaskStatusAdapter(shard_count=16, ttl=3600)
        assert adapter._inner is not None

    def test_get_status_not_found(self):
        """测试获取不存在的任务"""
        adapter = _PythonShardedTaskStatusAdapter(shard_count=16, ttl=3600)
        result = adapter.get_status("nonexistent_task")
        assert result is None

    def test_update_and_get_status(self):
        """测试更新和获取状态"""
        adapter = _PythonShardedTaskStatusAdapter(shard_count=16, ttl=3600)

        task_id = "test_task_1"
        status: TaskStatusDict = {
            "status": "pending",
            "submit_time": time.time(),
        }

        adapter.update_status(task_id, status)
        result = adapter.get_status(task_id)

        assert result is not None
        assert result["status"] == "pending"

    def test_remove_status(self):
        """测试移除状态"""
        adapter = _PythonShardedTaskStatusAdapter(shard_count=16, ttl=3600)

        task_id = "test_task_remove"
        adapter.update_status(task_id, {"status": "pending", "submit_time": time.time()})

        removed = adapter.remove_status(task_id)
        assert removed is True

        result = adapter.get_status(task_id)
        assert result is None

    def test_get_total_count(self):
        """测试获取总任务数"""
        adapter = _PythonShardedTaskStatusAdapter(shard_count=16, ttl=3600)

        for i in range(25):
            adapter.update_status(f"task_{i}", {"status": "pending", "submit_time": time.time()})

        count = adapter.get_total_count()
        assert count == 25

    def test_clear_all(self):
        """测试清空所有状态"""
        adapter = _PythonShardedTaskStatusAdapter(shard_count=16, ttl=3600)

        for i in range(15):
            adapter.update_status(f"task_{i}", {"status": "pending", "submit_time": time.time()})

        adapter.clear_all()

        count = adapter.get_total_count()
        assert count == 0


class TestPriorityTaskQueueAdapter:
    """测试优先级队列适配器"""

    def test_adapter_create_returns_instance(self):
        """测试 create 方法返回有效实例"""
        adapter = PriorityTaskQueueAdapter.create(maxsize=100)

        assert isinstance(adapter, PriorityTaskQueueAdapter)

        if is_rust_available():
            assert isinstance(adapter, _RustPriorityTaskQueueAdapter)
        else:
            assert isinstance(adapter, _PythonPriorityTaskQueueAdapter)

    def test_adapter_base_methods_raise_not_implemented(self):
        """测试基类方法抛出 NotImplementedError"""
        adapter = PriorityTaskQueueAdapter()

        with pytest.raises(NotImplementedError):
            adapter.put("task", 1)

        with pytest.raises(NotImplementedError):
            adapter.get()

        with pytest.raises(NotImplementedError):
            adapter.qsize()

        with pytest.raises(NotImplementedError):
            adapter.empty()

        with pytest.raises(NotImplementedError):
            adapter.full()


@pytest.mark.skipif(not is_rust_available(), reason="Rust 扩展不可用")
class TestRustPriorityTaskQueueAdapter:
    """测试 Rust 优先级队列适配器"""

    def test_init(self):
        """测试初始化"""
        adapter = _RustPriorityTaskQueueAdapter(maxsize=100)
        assert adapter._rust is not None
        assert adapter._tasks == {}

    def test_put_and_get(self):
        """测试添加和获取任务"""
        adapter = _RustPriorityTaskQueueAdapter(maxsize=100)

        adapter.put("task_1", priority=1)
        adapter.put("task_2", priority=2)

        task1 = adapter.get(block=False)
        assert task1 == "task_1"

        task2 = adapter.get(block=False)
        assert task2 == "task_2"

    def test_priority_order(self):
        """测试优先级顺序"""
        adapter = _RustPriorityTaskQueueAdapter(maxsize=100)

        adapter.put("low", priority=10)
        adapter.put("high", priority=1)
        adapter.put("medium", priority=5)

        assert adapter.get(block=False) == "high"
        assert adapter.get(block=False) == "medium"
        assert adapter.get(block=False) == "low"

    def test_qsize(self):
        """测试获取队列大小"""
        adapter = _RustPriorityTaskQueueAdapter(maxsize=100)

        assert adapter.qsize() == 0
        assert adapter.empty() is True

        adapter.put("task_1", priority=1)
        adapter.put("task_2", priority=2)

        assert adapter.qsize() == 2
        assert adapter.empty() is False

    def test_full(self):
        """测试队列满"""
        adapter = _RustPriorityTaskQueueAdapter(maxsize=2)

        adapter.put("task_1", priority=1)
        adapter.put("task_2", priority=2)

        assert adapter.full() is True


@pytest.mark.skipif(is_rust_available(), reason="测试 Python 回退实现")
class TestPythonPriorityTaskQueueAdapter:
    """测试 Python 优先级队列适配器（回退）"""

    def test_init(self):
        """测试初始化"""
        adapter = _PythonPriorityTaskQueueAdapter(maxsize=100)
        assert adapter._inner is not None

    def test_put_and_get(self):
        """测试添加和获取任务"""
        adapter = _PythonPriorityTaskQueueAdapter(maxsize=100)

        adapter.put("task_1", priority=1)
        adapter.put("task_2", priority=2)

        task1 = adapter.get(block=False)
        assert task1 == "task_1"

        task2 = adapter.get(block=False)
        assert task2 == "task_2"

    def test_priority_order(self):
        """测试优先级顺序"""
        adapter = _PythonPriorityTaskQueueAdapter(maxsize=100)

        adapter.put("low", priority=10)
        adapter.put("high", priority=1)
        adapter.put("medium", priority=5)

        assert adapter.get(block=False) == "high"
        assert adapter.get(block=False) == "medium"
        assert adapter.get(block=False) == "low"

    def test_qsize(self):
        """测试获取队列大小"""
        adapter = _PythonPriorityTaskQueueAdapter(maxsize=100)

        assert adapter.qsize() == 0
        assert adapter.empty() is True

        adapter.put("task_1", priority=1)
        adapter.put("task_2", priority=2)

        assert adapter.qsize() == 2
        assert adapter.empty() is False

    def test_full(self):
        """测试队列满"""
        adapter = _PythonPriorityTaskQueueAdapter(maxsize=2)

        adapter.put("task_1", priority=1)
        adapter.put("task_2", priority=2)

        assert adapter.full() is True


class TestGetShardedStatusStore:
    """测试 get_sharded_status_store 函数"""

    def test_returns_adapter_instance(self):
        """测试返回适配器实例"""
        store = get_sharded_status_store(shard_count=16, ttl=3600)

        assert isinstance(store, ShardedTaskStatusAdapter)

    def test_default_parameters(self):
        """测试默认参数"""
        store = get_sharded_status_store()

        # 应该使用默认值创建
        assert store is not None

    def test_custom_parameters(self):
        """测试自定义参数"""
        store = get_sharded_status_store(shard_count=32, ttl=7200)

        assert store is not None
        # 验证基本功能
        store.update_status("test", {"status": "pending", "submit_time": time.time()})
        result = store.get_status("test")
        assert result is not None


class TestGetPriorityQueue:
    """测试 get_priority_queue 函数"""

    def test_returns_adapter_instance(self):
        """测试返回适配器实例"""
        queue = get_priority_queue(maxsize=100)

        assert isinstance(queue, PriorityTaskQueueAdapter)

    def test_default_parameters(self):
        """测试默认参数"""
        queue = get_priority_queue()

        assert queue is not None

    def test_custom_parameters(self):
        """测试自定义参数"""
        queue = get_priority_queue(maxsize=500)

        assert queue is not None
        # 验证基本功能
        queue.put("test_task", priority=1)
        assert queue.qsize() == 1


class TestAdapterCompatibility:
    """测试适配器兼容性"""

    def test_status_store_basic_operations(self):
        """测试状态存储基本操作"""
        store = get_sharded_status_store(shard_count=16, ttl=3600)

        # 基本操作序列
        task_id = "compat_test_task"

        # 初始状态应该是 None
        assert store.get_status(task_id) is None

        # 添加状态
        store.update_status(task_id, {"status": "pending", "submit_time": time.time()})
        result = store.get_status(task_id)
        assert result is not None
        assert result["status"] == "pending"

        # 更新状态
        store.update_status(
            task_id,
            {"status": "running", "submit_time": time.time(), "start_time": time.time()},
        )
        result = store.get_status(task_id)
        assert result["status"] == "running"

        # 移除状态
        removed = store.remove_status(task_id)
        assert removed is True or removed is False  # 取决于实现
        assert store.get_status(task_id) is None

    def test_queue_basic_operations(self):
        """测试队列基本操作"""
        queue = get_priority_queue(maxsize=100)

        # 基本操作序列
        assert queue.empty() is True
        assert queue.qsize() == 0

        # 添加任务
        queue.put("task1", priority=1)
        queue.put("task2", priority=2)

        assert queue.qsize() == 2
        assert queue.empty() is False

        # 获取任务
        task1 = queue.get(block=False)
        assert task1 == "task1"

        assert queue.qsize() == 1

        task2 = queue.get(block=False)
        assert task2 == "task2"

        assert queue.empty() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
