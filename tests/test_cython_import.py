"""Cython 模块导入测试

验证 Cython 模块可正确导入和回退到纯 Python 实现。
"""

import sys
from pathlib import Path

import pytest


# 测试 Cython 模块导入
def test_cython_module_import():
    """测试 Cython 模块可以正确导入"""
    try:
        from fish_async_task._cython import ShardedTaskStatus as CythonShardedTaskStatus

        # 如果导入成功，验证它是一个类
        assert callable(CythonShardedTaskStatus)
    except ImportError:
        # 如果 Cython 模块不可用，测试应该通过（回退到纯 Python）
        pytest.skip("Cython 模块未编译，跳过测试")


def test_cython_fallback_to_python():
    """测试 Cython 不可用时回退到纯 Python 实现"""
    from fish_async_task.performance import ShardedTaskStatus

    # 验证纯 Python 实现可用
    assert ShardedTaskStatus is not None
    assert callable(ShardedTaskStatus)

    # 创建实例
    store = ShardedTaskStatus(shard_count=16)
    assert store is not None


def test_cython_availability_detection():
    """测试 Cython 可用性检测"""
    from fish_async_task._cython import CYTHON_AVAILABLE

    # CYTHON_AVAILABLE 应该是一个布尔值
    assert isinstance(CYTHON_AVAILABLE, bool)

    # 如果 Cython 可用，验证模块可以导入
    if CYTHON_AVAILABLE:
        from fish_async_task._cython import ShardedTaskStatus

        assert ShardedTaskStatus is not None


def test_python_always_available():
    """测试纯 Python 实现始终可用"""
    from fish_async_task.performance import ShardedTaskStatus

    # 纯 Python 实现应该始终可用
    assert ShardedTaskStatus is not None

    # 验证基本功能
    store = ShardedTaskStatus()
    assert store.get_status("nonexistent") is None
    assert store.get_task_count() == 0


def test_cython_python_api_compatibility():
    """测试 Cython 和纯 Python 实现 API 一致性"""
    from fish_async_task.performance import ShardedTaskStatus as PythonShardedTaskStatus

    # 测试纯 Python 实现的 API
    python_store = PythonShardedTaskStatus(shard_count=16)

    # 基本操作
    python_store.update_status("task-1", {"status": "running"})
    assert python_store.get_status("task-1")["status"] == "running"
    assert python_store.get_task_count() == 1
    python_store.remove_status("task-1")
    assert python_store.get_task_count() == 0

    # 如果 Cython 可用，测试 Cython 实现的 API
    try:
        from fish_async_task._cython import ShardedTaskStatus as CythonShardedTaskStatus

        cython_store = CythonShardedTaskStatus(shard_count=16)

        # 相同的操作应该产生相同的结果
        cython_store.update_status("task-1", {"status": "running"})
        assert cython_store.get_status("task-1")["status"] == "running"
        assert cython_store.get_task_count() == 1
        cython_store.remove_status("task-1")
        assert cython_store.get_task_count() == 0

    except ImportError:
        pytest.skip("Cython 模块未编译，跳过 API 兼容性测试")


def test_performance_module_auto_detection():
    """测试 performance 模块自动检测最佳实现"""
    from fish_async_task.performance import ShardedTaskStatus

    # 验证导入成功
    assert ShardedTaskStatus is not None

    # 创建实例并测试基本功能
    store = ShardedTaskStatus(shard_count=16)
    store.update_status("task-1", {"status": "pending"})
    status = store.get_status("task-1")

    assert status is not None
    assert status["status"] == "pending"
