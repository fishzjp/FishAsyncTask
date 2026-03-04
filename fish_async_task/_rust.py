"""Rust 扩展模块导入适配器"""

# 尝试导入 Rust 实现的扩展
try:
    from fish_async_task._core import (
        PyPriorityTaskQueue,
        PyShardedTaskStatus,
        PyTaskDependencyManager,
    )

    _RUST_AVAILABLE = True
except ImportError:
    _RUST_AVAILABLE = False
    PyShardedTaskStatus = None
    PyPriorityTaskQueue = None
    PyTaskDependencyManager = None


def is_rust_available() -> bool:
    """检查 Rust 扩展是否可用"""
    return _RUST_AVAILABLE
