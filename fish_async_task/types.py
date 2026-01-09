"""
类型定义模块

定义任务管理器相关的类型别名和类型定义。
"""

from typing import Any, Callable, Dict, Literal, Optional, Tuple, TypedDict, Union

# 类型别名
# TaskTuple: (task_id, func, args, kwargs)
# - task_id: 任务ID（字符串）
# - func: 要执行的任务函数
# - args: 任务函数的位置参数（元组）
# - kwargs: 任务函数的关键字参数（字典）
TaskTuple = Tuple[str, Callable[..., Any], Tuple[Any, ...], Dict[str, Any]]
TaskStatus = Literal["pending", "running", "completed", "failed"]


class TaskStatusDict(TypedDict, total=False):
    """
    任务状态字典类型定义

    所有字段都是可选的（total=False），因为不同状态的任务包含的字段不同：
    - pending: status, submit_time
    - running: status, submit_time, start_time
    - completed: status, submit_time, start_time, end_time, result
    - failed: status, submit_time, start_time, end_time, error

    所有可选字段都使用 Optional 注解，明确标识该字段可能为 None。
    """

    status: Optional[TaskStatus]  # pending, running, completed, failed
    submit_time: Optional[float]  # 任务提交时间（Unix时间戳）
    start_time: Optional[float]  # 任务开始执行时间（Unix时间戳）
    end_time: Optional[float]  # 任务结束时间（Unix时间戳）
    result: Optional[Any]  # 任务执行结果（仅completed状态）
    error: Optional[str]  # 错误信息（仅failed状态）
    worker_id: Optional[str]  # 执行任务的工作线程ID（性能优化新增）


# 性能优化相关类型定义
class ShardedTaskStatusDict(TypedDict):
    """分片任务状态字典，包含分片索引信息"""

    shard_index: int  # 分片索引
    task_status: TaskStatusDict  # 任务状态数据


class BatchedUpdate(TypedDict):
    """批量更新项"""

    task_id: str
    status: TaskStatusDict


class ScalingMetrics(TypedDict):
    """自适应扩展指标"""

    current_workers: int  # 当前工作线程数
    avg_task_time: float  # 平均任务执行时间（秒）
    cpu_usage: Optional[float]  # CPU 使用率（0-1），如果 psutil 不可用则为 None
    last_scale_up_time: float  # 上次扩展时间（Unix时间戳）
    last_scale_down_time: float  # 上次缩减时间（Unix时间戳）
    queue_size: int  # 当前队列大小
