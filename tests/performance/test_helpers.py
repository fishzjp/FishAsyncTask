"""
性能测试辅助函数

本模块提供性能测试的辅助工具函数。
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple


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
    return count / elapsed if elapsed > 0 else 0.0


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
        "mean": sum(latencies) / len(latencies) if latencies else 0.0,
    }


def run_concurrent_queries(
    func: Callable[..., Any],
    num_threads: int,
    queries_per_thread: int,
) -> Tuple[float, Dict[str, float]]:
    """
    运行并发查询并测量性能

    Args:
        func: 要执行的查询函数
        num_threads: 并发线程数
        queries_per_thread: 每个线程的查询数

    Returns:
        (QPS, 延迟分布字典)
    """
    results = []
    lock = threading.Lock()

    def worker() -> None:
        """工作线程函数"""
        thread_latencies = []
        for _ in range(queries_per_thread):
            start = time.perf_counter()
            func()
            end = time.perf_counter()
            thread_latencies.append((end - start) * 1000)  # 毫秒

        with lock:
            results.extend(thread_latencies)

    # 记录总时间
    start_time = time.perf_counter()

    # 使用线程池执行
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker) for _ in range(num_threads)]
        for future in as_completed(futures):
            future.result()  # 等待完成

    elapsed = time.perf_counter() - start_time

    # 计算 QPS
    total_queries = num_threads * queries_per_thread
    qps = total_queries / elapsed if elapsed > 0 else 0.0

    # 计算延迟分布
    results.sort()
    latency_dist = {
        "p50": results[len(results) // 2],
        "p95": results[int(len(results) * 0.95)],
        "p99": results[int(len(results) * 0.99)],
        "min": results[0],
        "max": results[-1],
        "mean": sum(results) / len(results) if results else 0.0,
    }

    return qps, latency_dist


def create_task_statuses(count: int, base_time: Optional[float] = None) -> List[Dict[str, Any]]:
    """
    创建测试用的任务状态列表

    Args:
        count: 任务数量
        base_time: 基准时间（Unix 时间戳），如果为 None 则使用当前时间

    Returns:
        任务状态字典列表
    """
    if base_time is None:
        base_time = time.time()

    statuses = []
    for i in range(count):
        statuses.append({
            "task_id": f"task-{i}",
            "status": "completed",
            "submit_time": base_time,
            "start_time": base_time + 0.1,
            "end_time": base_time + 0.2,
            "result": f"result-{i}",
        })

    return statuses


def assert_performance_meets_threshold(
    actual_value: float,
    threshold: float,
    metric_name: str,
    comparison: str = "min",
) -> None:
    """
    断言性能值满足阈值要求

    Args:
        actual_value: 实际性能值
        threshold: 阈值
        metric_name: 指标名称（用于错误消息）
        comparison: 比较类型，"min" 表示 actual_value 必须 >= threshold，
                   "max" 表示 actual_value 必须 <= threshold

    Raises:
        AssertionError: 如果性能值不满足阈值
    """
    if comparison == "min":
        assert actual_value >= threshold, \
            f"{metric_name} 不满足要求: 实际值 {actual_value:.2f} < 阈值 {threshold:.2f}"
    elif comparison == "max":
        assert actual_value <= threshold, \
            f"{metric_name} 不满足要求: 实际值 {actual_value:.2f} > 阈值 {threshold:.2f}"
    else:
        raise ValueError(f"无效的比较类型: {comparison}，必须是 'min' 或 'max'")
