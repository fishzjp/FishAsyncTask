"""
性能测试配置和共享 fixtures

本模块提供性能测试的共享配置和辅助工具。
"""

import time
from typing import Any, Callable, Dict

import pytest

from fish_async_task.task_manager import TaskManager


class TestConfig:
    """
    性能测试配置类

    定义测试中使用的各种常量和参数
    """

    # 任务数量配置
    TASK_COUNT_SMALL = 100
    TASK_COUNT_MEDIUM = 1000
    TASK_COUNT_LARGE = 5000

    # 并发线程数配置
    CONCURRENT_THREADS_SMALL = 10
    CONCURRENT_THREADS_MEDIUM = 50
    CONCURRENT_THREADS_LARGE = 100

    # 超时配置（秒）
    TEST_TIMEOUT = 30
    TEST_TIMEOUT_LONG = 120

    # 性能阈值
    QPS_MIN = 8000.0
    P99_LATENCY_MAX_MS = 5.0
    CLEANUP_TIME_10K_MAX_MS = 10.0
    SUBMISSION_THROUGHPUT_MIN = 5000.0


@pytest.fixture
def benchmark_timer() -> Dict[str, float]:
    """
    提供简单的计时器 fixture

    Returns:
        包含 'start' 和 'end' 方法的字典
    """
    times: Dict[str, float] = {}

    def start() -> None:
        """开始计时"""
        times["start"] = time.perf_counter()

    def end() -> float:
        """结束计时并返回耗时（毫秒）"""
        times["end"] = time.perf_counter()
        return (times["end"] - times["start"]) * 1000

    return {"start": start, "end": end}


@pytest.fixture
def performance_threshold() -> Dict[str, float]:
    """
    提供性能阈值配置

    Returns:
        包含各种性能阈值的字典
    """
    return {
        # 状态查询性能阈值
        "qps_min": 8000.0,  # 最小 QPS
        "p99_latency_max_ms": 5.0,  # 最大 P99 延迟（毫秒）
        "p95_latency_max_ms": 2.0,  # 最大 P95 延迟（毫秒）
        # 清理性能阈值
        "cleanup_time_10k_max_ms": 10.0,  # 10k 任务清理最大时间
        # 任务提交吞吐量阈值
        "submission_throughput_min": 5000.0,  # 最小提交吞吐量（任务/秒）
        # 内存使用阈值
        "memory_reduction_min_percent": 20.0,  # 最小内存减少百分比
    }


def measure_qps(func: Callable[..., Any], duration_sec: float = 1.0) -> float:
    """
    测量函数的 QPS（每秒查询数）

    Args:
        func: 要测量的函数
        duration_sec: 测量持续时间（秒）

    Returns:
        QPS 值
    """
    start_time = time.perf_counter()
    count = 0

    while time.perf_counter() - start_time < duration_sec:
        func()
        count += 1

    elapsed = time.perf_counter() - start_time
    return count / elapsed


def measure_latency(func: Callable[..., Any], iterations: int = 1000) -> Dict[str, float]:
    """
    测量函数的延迟分布

    Args:
        func: 要测量的函数
        iterations: 迭代次数

    Returns:
        包含 p50, p95, p99 延迟的字典（毫秒）
    """
    latencies = []

    for _ in range(iterations):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        latencies.append((end - start) * 1000)  # 转换为毫秒

    latencies.sort()

    return {
        "p50": latencies[len(latencies) // 2],
        "p95": latencies[int(len(latencies) * 0.95)],
        "p99": latencies[int(len(latencies) * 0.99)],
        "min": latencies[0],
        "max": latencies[-1],
        "mean": sum(latencies) / len(latencies),
    }


def cleanup_task_manager_instances() -> None:
    """
    清理所有 TaskManager 单例实例

    用于测试隔离，确保每个测试开始时没有残留的实例
    """
    TaskManager._instances.clear()


def create_test_tasks(
    task_manager: TaskManager,
    count: int,
    task_func: Callable,
    *args: Any,
    **kwargs: Any,
) -> list[str]:
    """
    创建测试任务

    Args:
        task_manager: TaskManager 实例
        count: 任务数量
        task_func: 任务函数
        *args: 任务函数的位置参数
        **kwargs: 任务函数的关键字参数

    Returns:
        任务 ID 列表
    """
    task_ids = []
    for _ in range(count):
        task_id = task_manager.submit_task(task_func, *args, **kwargs)
        task_ids.append(task_id)
    return task_ids


def wait_for_all_tasks(
    task_manager: TaskManager,
    task_ids: list[str],
    timeout: float = 30.0,
    check_interval: float = 0.1,
) -> bool:
    """
    等待所有任务完成

    Args:
        task_manager: TaskManager 实例
        task_ids: 任务 ID 列表
        timeout: 超时时间（秒）
        check_interval: 检查间隔（秒）

    Returns:
        是否所有任务都在超时时间内完成
    """
    waited = 0.0
    while waited < timeout:
        all_completed = True
        for task_id in task_ids:
            status = task_manager.get_task_status(task_id)
            if not status or status["status"] not in ("completed", "failed"):
                all_completed = False
                break
        if all_completed:
            return True
        time.sleep(check_interval)
        waited += check_interval
    return False


def wait_for_task_completion(
    task_manager: TaskManager,
    task_id: str,
    timeout: float = 30.0,
    check_interval: float = 0.1,
) -> bool:
    """
    等待单个任务完成

    Args:
        task_manager: TaskManager 实例
        task_id: 任务 ID
        timeout: 超时时间（秒）
        check_interval: 检查间隔（秒）

    Returns:
        是否任务在超时时间内完成
    """
    waited = 0.0
    while waited < timeout:
        status = task_manager.get_task_status(task_id)
        if status and status["status"] in ("completed", "failed"):
            return True
        time.sleep(check_interval)
        waited += check_interval
    return False


def print_test_header(
    test_name: str,
    task_count: int = 0,
    concurrent: int = 0,
    **kwargs: Any,
) -> None:
    """
    打印测试开始的头部信息

    Args:
        test_name: 测试名称
        task_count: 任务数量
        concurrent: 并发数
        **kwargs: 其他要显示的参数
    """
    print(f"\n{'=' * 80}")
    print(f"测试: {test_name}")
    if task_count > 0:
        print(f"任务数量: {task_count}")
    if concurrent > 0:
        print(f"并发线程: {concurrent}")
    for key, value in kwargs.items():
        print(f"{key}: {value}")
    print(f"{'=' * 80}\n")


def print_test_footer(execution_time: float, **metrics: Any) -> None:
    """
    打印测试结束的尾部信息

    Args:
        execution_time: 执行时间（秒）
        **metrics: 其他性能指标
    """
    print(f"\n{'=' * 80}")
    print(f"执行时间: {execution_time:.3f}秒")
    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"{key}: {value:.3f}")
        else:
            print(f"{key}: {value}")
    print(f"{'=' * 80}\n")

