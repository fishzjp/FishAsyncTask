"""
类型定义测试模块

测试 types.py 中定义的类型别名和 TypedDict。
"""

import time
from typing import get_args, get_origin

import pytest

from fish_async_task.types import (
    BatchedUpdate,
    ScalingMetrics,
    ShardedTaskStatusDict,
    TaskStatus,
    TaskStatusDict,
    TaskTuple,
)


class TestTaskStatus:
    """测试 TaskStatus 字面量类型"""

    def test_valid_status_values(self):
        """测试有效的状态值"""
        valid_statuses = ["pending", "running", "completed", "failed"]

        for status in valid_statuses:
            # 验证类型检查通过
            assert status in get_args(TaskStatus)

    def test_invalid_status_rejected(self):
        """测试无效状态值"""
        invalid_statuses = ["invalid", "PENDING", "Pending", None, 123]

        for status in invalid_statuses:
            assert status not in get_args(TaskStatus)


class TestTaskStatusDict:
    """测试 TaskStatusDict TypedDict"""

    def test_pending_status_dict(self):
        """测试 pending 状态字典"""
        status: TaskStatusDict = {
            "status": "pending",
            "submit_time": time.time(),
        }
        assert status["status"] == "pending"
        assert "submit_time" in status

    def test_running_status_dict(self):
        """测试 running 状态字典"""
        now = time.time()
        status: TaskStatusDict = {
            "status": "running",
            "submit_time": now - 1,
            "start_time": now,
        }
        assert status["status"] == "running"
        assert "start_time" in status

    def test_completed_status_dict(self):
        """测试 completed 状态字典"""
        now = time.time()
        status: TaskStatusDict = {
            "status": "completed",
            "submit_time": now - 2,
            "start_time": now - 1,
            "end_time": now,
            "result": 42,
        }
        assert status["status"] == "completed"
        assert status["result"] == 42

    def test_failed_status_dict(self):
        """测试 failed 状态字典"""
        now = time.time()
        status: TaskStatusDict = {
            "status": "failed",
            "submit_time": now - 2,
            "start_time": now - 1,
            "end_time": now,
            "error": "Test error",
        }
        assert status["status"] == "failed"
        assert status["error"] == "Test error"

    def test_all_fields_optional(self):
        """测试所有字段都是可选的"""
        # 空字典应该是有效的（虽然不是实际使用场景）
        status: TaskStatusDict = {}
        assert isinstance(status, dict)

        # 只有部分字段
        partial_status: TaskStatusDict = {"status": "pending"}
        assert partial_status["status"] == "pending"

    def test_worker_id_field(self):
        """测试 worker_id 字段"""
        status: TaskStatusDict = {
            "status": "running",
            "submit_time": time.time(),
            "start_time": time.time(),
            "worker_id": "worker-123",
        }
        assert status["worker_id"] == "worker-123"

    def test_result_and_error_mutually_exclusive(self):
        """测试 result 和 error 字段通常是互斥的"""
        # completed 状态应该有 result
        completed: TaskStatusDict = {
            "status": "completed",
            "submit_time": time.time(),
            "start_time": time.time(),
            "end_time": time.time(),
            "result": "success",
        }
        assert "result" in completed
        assert "error" not in completed

        # failed 状态应该有 error
        failed: TaskStatusDict = {
            "status": "failed",
            "submit_time": time.time(),
            "start_time": time.time(),
            "end_time": time.time(),
            "error": "Something went wrong",
        }
        assert "error" in failed
        assert "result" not in failed


class TestTaskTuple:
    """测试 TaskTuple 类型别名"""

    def test_task_tuple_structure(self):
        """测试任务元组结构"""
        def sample_task(x: int, y: int) -> int:
            return x + y

        task_id = "test-123"
        args = (1, 2)
        kwargs = {"z": 3}

        task: TaskTuple = (task_id, sample_task, args, kwargs)

        assert task[0] == task_id
        assert task[1] == sample_task
        assert task[2] == args
        assert task[3] == kwargs

    def test_task_tuple_execution(self):
        """测试通过 TaskTuple 执行任务"""
        def add(a: int, b: int) -> int:
            return a + b

        task: TaskTuple = ("task-1", add, (3, 5), {})
        _, func, args, kwargs = task

        result = func(*args, **kwargs)
        assert result == 8

    def test_task_tuple_with_kwargs(self):
        """测试带关键字参数的 TaskTuple"""
        def greet(name: str, greeting: str = "Hello") -> str:
            return f"{greeting}, {name}!"

        task: TaskTuple = ("task-2", greet, (), {"name": "World", "greeting": "Hi"})
        _, func, args, kwargs = task

        result = func(*args, **kwargs)
        assert result == "Hi, World!"


class TestShardedTaskStatusDict:
    """测试 ShardedTaskStatusDict TypedDict"""

    def test_sharded_status_structure(self):
        """测试分片状态结构"""
        task_status: TaskStatusDict = {
            "status": "pending",
            "submit_time": time.time(),
        }

        sharded: ShardedTaskStatusDict = {
            "shard_index": 5,
            "task_status": task_status,
        }

        assert sharded["shard_index"] == 5
        assert sharded["task_status"]["status"] == "pending"

    def test_sharded_status_with_completed_task(self):
        """测试带完成任务的分片状态"""
        task_status: TaskStatusDict = {
            "status": "completed",
            "submit_time": time.time() - 2,
            "start_time": time.time() - 1,
            "end_time": time.time(),
            "result": "done",
        }

        sharded: ShardedTaskStatusDict = {
            "shard_index": 0,
            "task_status": task_status,
        }

        assert sharded["task_status"]["result"] == "done"


class TestBatchedUpdate:
    """测试 BatchedUpdate TypedDict"""

    def test_batched_update_structure(self):
        """测试批量更新结构"""
        status: TaskStatusDict = {
            "status": "running",
            "submit_time": time.time(),
        }

        update: BatchedUpdate = {
            "task_id": "task-123",
            "status": status,
        }

        assert update["task_id"] == "task-123"
        assert update["status"]["status"] == "running"

    def test_batched_update_with_multiple_statuses(self):
        """测试多个批量更新"""
        updates = []
        for i in range(3):
            status: TaskStatusDict = {
                "status": "pending" if i < 2 else "running",
                "submit_time": time.time(),
            }
            update: BatchedUpdate = {
                "task_id": f"task-{i}",
                "status": status,
            }
            updates.append(update)

        assert len(updates) == 3
        assert updates[0]["task_id"] == "task-0"
        assert updates[2]["status"]["status"] == "running"


class TestScalingMetrics:
    """测试 ScalingMetrics TypedDict"""

    def test_scaling_metrics_structure(self):
        """测试扩展指标结构"""
        now = time.time()
        metrics: ScalingMetrics = {
            "current_workers": 5,
            "avg_task_time": 0.5,
            "cpu_usage": 0.75,
            "last_scale_up_time": now - 100,
            "last_scale_down_time": now - 200,
            "queue_size": 10,
        }

        assert metrics["current_workers"] == 5
        assert metrics["cpu_usage"] == 0.75
        assert metrics["queue_size"] == 10

    def test_scaling_metrics_without_cpu(self):
        """测试没有 CPU 使用的指标（psutil 不可用时）"""
        now = time.time()
        metrics: ScalingMetrics = {
            "current_workers": 3,
            "avg_task_time": 1.0,
            "cpu_usage": None,  # psutil 不可用
            "last_scale_up_time": now - 50,
            "last_scale_down_time": now - 150,
            "queue_size": 5,
        }

        assert metrics["current_workers"] == 3
        assert metrics["cpu_usage"] is None


class TypeCoercionTests:
    """测试类型转换和边界情况"""

    def test_none_values_in_status_dict(self):
        """测试状态字典中的 None 值"""
        status: TaskStatusDict = {
            "status": None,
            "submit_time": None,
            "start_time": None,
            "end_time": None,
            "result": None,
            "error": None,
        }
        # 所有字段都可以是 None
        assert status["status"] is None

    def test_numeric_timestamps(self):
        """测试数字时间戳"""
        # 浮点数时间戳
        status: TaskStatusDict = {
            "status": "pending",
            "submit_time": 1234567890.123,
        }
        assert isinstance(status["submit_time"], float)

        # 整数时间戳
        status2: TaskStatusDict = {
            "status": "pending",
            "submit_time": 1234567890,
        }
        assert isinstance(status2["submit_time"], (int, float))

    def test_any_result_type(self):
        """测试 result 可以是任何类型"""
        # 字符串结果
        status1: TaskStatusDict = {
            "status": "completed",
            "result": "success",
        }

        # 数字结果
        status2: TaskStatusDict = {
            "status": "completed",
            "result": 42,
        }

        # 字典结果
        status3: TaskStatusDict = {
            "status": "completed",
            "result": {"key": "value"},
        }

        # 列表结果
        status4: TaskStatusDict = {
            "status": "completed",
            "result": [1, 2, 3],
        }

        # None 结果
        status5: TaskStatusDict = {
            "status": "completed",
            "result": None,
        }

        assert status1["result"] == "success"
        assert status2["result"] == 42
        assert status3["result"]["key"] == "value"
        assert status4["result"] == [1, 2, 3]
        assert status5["result"] is None


class TestTypeValidation:
    """测试类型验证"""

    def test_task_status_literal_values(self):
        """测试 TaskStatus 只允许特定值"""
        allowed = get_args(TaskStatus)
        assert "pending" in allowed
        assert "running" in allowed
        assert "completed" in allowed
        assert "failed" in allowed
        assert len(allowed) == 4

    def test_task_tuple_types(self):
        """测试 TaskTuple 的类型"""
        # 这只是运行时验证，实际类型检查需要 mypy
        def task_func():
            return "done"

        task: TaskTuple = ("id", task_func, (), {})
        assert isinstance(task[0], str)
        assert callable(task[1])
        assert isinstance(task[2], tuple)
        assert isinstance(task[3], dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
