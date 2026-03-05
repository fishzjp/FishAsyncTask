"""
冒烟测试 - 验证核心功能基本可用

这些测试应该快速运行，确保基本功能正常。
"""
import time

import pytest

from fish_async_task import TaskManager
from fish_async_task.task_manager import TaskManager as TaskManagerClass


@pytest.fixture(autouse=True)
def cleanup_instances():
    """每个测试前后清理单例实例"""
    TaskManagerClass._instances.clear()
    yield
    TaskManagerClass._instances.clear()


def simple_task(value: int):
    """简单的测试任务"""
    return value * 2


def wait_for_completion(task_manager, task_id, timeout=5):
    """等待任务完成"""
    waited = 0
    while waited < timeout:
        status = task_manager.get_task_status(task_id)
        if status and status["status"] in ("completed", "failed"):
            return status
        time.sleep(0.05)
        waited += 0.05
    return None


@pytest.mark.smoke
def test_task_submit_and_execute():
    """测试：能够提交任务并执行完成"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()

    task_id = task_manager.submit_task(simple_task, 21)
    assert task_id is not None

    status = wait_for_completion(task_manager, task_id)
    assert status is not None
    assert status["status"] == "completed"
    assert status["result"] == 42

    task_manager.shutdown()


@pytest.mark.smoke
def test_task_manager_singleton():
    """测试：TaskManager 单例模式工作"""
    tm1 = TaskManager()
    tm2 = TaskManager()
    assert tm1 is tm2

    tm1.shutdown()


@pytest.mark.smoke
def test_rust_extension_available():
    """测试：Rust 扩展可用"""
    from fish_async_task._rust import is_rust_available

    # Rust 扩展应该可用
    assert is_rust_available() is True


@pytest.mark.smoke
def test_task_status_storage():
    """测试：任务状态存储基本功能"""
    from fish_async_task._rust import PyShardedTaskStatus

    storage = PyShardedTaskStatus(2, 3600)

    # 创建并获取任务状态
    task_id = "smoke_test_001"
    initial_status = {"status": "pending"}
    storage.update_status(task_id, initial_status)

    # 获取状态
    status = storage.get_status(task_id)
    assert status is not None
    assert status["status"] == "pending"

    # 更新状态为完成
    updated_status = {"status": "completed"}
    storage.update_status(task_id, updated_status)
    status = storage.get_status(task_id)
    assert status["status"] == "completed"
