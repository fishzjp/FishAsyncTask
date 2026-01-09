"""
并发测试辅助函数

本模块提供并发测试的辅助工具函数。
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List


def run_concurrent_operations(
    func: Callable[..., Any],
    num_threads: int,
    operations_per_thread: int = 1,
    **kwargs: Any,
) -> List[Any]:
    """
    运行并发操作

    Args:
        func: 要执行的函数
        num_threads: 并发线程数
        operations_per_thread: 每个线程的操作数
        **kwargs: 传递给函数的其他参数

    Returns:
        所有操作的返回值列表
    """
    results = []

    def worker() -> List[Any]:
        """工作线程函数"""
        thread_results = []
        for _ in range(operations_per_thread):
            result = func(**kwargs)
            thread_results.append(result)
        return thread_results

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker) for _ in range(num_threads)]
        for future in as_completed(futures):
            results.extend(future.result())

    return results


def assert_no_data_corruption(
    original_data: Dict[Any, Any],
    accessed_data: Dict[Any, Any],
) -> None:
    """
    断言并发访问后数据没有损坏

    Args:
        original_data: 原始数据
        accessed_data: 并发访问后的数据

    Raises:
        AssertionError: 如果数据损坏
    """
    assert len(original_data) == len(accessed_data), \
        f"数据长度不匹配: 原始 {len(original_data)} vs 访问后 {len(accessed_data)}"

    for key in original_data:
        assert key in accessed_data, f"键丢失: {key}"
        assert original_data[key] == accessed_data[key], \
            f"值不匹配: 键 {key}, 原始 {original_data[key]} vs 访问后 {accessed_data[key]}"


def detect_deadlock(
    func: Callable[..., Any],
    timeout_sec: float = 5.0,
    **kwargs: Any,
) -> bool:
    """
    检测函数是否会发生死锁

    Args:
        func: 要测试的函数
        timeout_sec: 超时时间（秒）
        **kwargs: 传递给函数的参数

    Returns:
        True 如果检测到死锁（超时），False 否则
    """
    def worker() -> bool:
        """工作线程函数"""
        try:
            func(**kwargs)
            return False  # 无死锁
        except Exception:
            return True  # 发生异常，可能死锁

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=timeout_sec)

    if thread.is_alive():
        # 线程仍在运行，可能死锁
        return True

    return False


def measure_lock_contention(
    func: Callable[..., Any],
    num_threads: int,
    iterations: int = 100,
) -> Dict[str, float]:
    """
    测量锁竞争情况

    Args:
        func: 要测量的函数
        num_threads: 并发线程数
        iterations: 每个线程的迭代次数

    Returns:
        包含锁竞争指标的字典：
        - total_time: 总时间（秒）
        - avg_time_per_op: 平均每次操作时间（毫秒）
        - throughput: 吞吐量（操作/秒）
    """
    start_time = time.perf_counter()

    def worker() -> None:
        """工作线程函数"""
        for _ in range(iterations):
            func()

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker) for _ in range(num_threads)]
        for future in as_completed(futures):
            future.result()

    end_time = time.perf_counter()
    total_time = end_time - start_time
    total_ops = num_threads * iterations

    return {
        "total_time": total_time,
        "avg_time_per_op": (total_time * 1000) / total_ops if total_ops > 0 else 0.0,
        "throughput": total_ops / total_time if total_time > 0 else 0.0,
    }
