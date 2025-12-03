"""
类型定义模块

定义任务管理器相关的类型别名和类型定义。
"""

from typing import Any, Callable, Dict, Literal, Tuple, TypedDict

# 类型别名
TaskTuple = Tuple[str, Callable[..., Any], tuple, dict]
TaskStatus = Literal["pending", "running", "completed", "failed"]


class TaskStatusDict(TypedDict, total=False):
    """任务状态字典类型定义"""
    status: TaskStatus  # pending, running, completed, failed
    submit_time: float
    start_time: float
    end_time: float
    result: Any
    error: str

