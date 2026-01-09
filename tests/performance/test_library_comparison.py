"""
多库性能对比测试

对比 FishAsyncTask、concurrent.futures、huey、dramatiq 的性能差异。

测试场景：
- 任务提交吞吐量
- 任务执行时间
- 并发状态查询
- 清理过期任务
- 端到端性能
- 可扩展性测试

测试指标：
- 吞吐量 (tasks/second)
- 延迟分布 (P50, P90, P95, P99, P99.9)
- 成功率 (%)
- CPU 使用率 (%)
- 内存占用 (MB)
"""

import gc
import os
import queue
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

import psutil
import pytest

# 导入 FishAsyncTask 相关模块
from fish_async_task.task_manager import TaskManager as FishTaskManager
from tests.performance.conftest import (
    TestConfig,
    cleanup_task_manager_instances,
    create_test_tasks,
    print_test_footer,
    print_test_header,
    wait_for_all_tasks,
)
from tests.performance.utils import PerformanceMetrics, ThroughputTracker


class ConcurrentFuturesStatusTracker:
    """
    concurrent.futures 任务状态追踪器
    
    为 ThreadPoolExecutor 实现类似 FishAsyncTask 的任务状态追踪功能。
    由于 concurrent.futures 不提供内置的状态查询，需要手动实现。
    """
    
    def __init__(self) -> None:
        """初始化状态追踪器"""
        self._status: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
    
    def set_pending(self, task_id: str, submit_time: float) -> None:
        """设置任务为 pending 状态"""
        with self._lock:
            self._status[task_id] = {
                "status": "pending",
                "submit_time": submit_time,
                "start_time": None,
                "end_time": None,
                "result": None,
                "error": None,
            }
    
    def set_running(self, task_id: str, start_time: float) -> None:
        """设置任务为 running 状态"""
        with self._lock:
            if task_id in self._status:
                self._status[task_id]["status"] = "running"
                self._status[task_id]["start_time"] = start_time
    
    def set_completed(self, task_id: str, end_time: float, result: Any) -> None:
        """设置任务为 completed 状态"""
        with self._lock:
            if task_id in self._status:
                self._status[task_id]["status"] = "completed"
                self._status[task_id]["end_time"] = end_time
                self._status[task_id]["result"] = result
    
    def set_failed(self, task_id: str, end_time: float, error: str) -> None:
        """设置任务为 failed 状态"""
        with self._lock:
            if task_id in self._status:
                self._status[task_id]["status"] = "failed"
                self._status[task_id]["end_time"] = end_time
                self._status[task_id]["error"] = error
    
    def get_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        with self._lock:
            return self._status.get(task_id)
    
    def clear(self, task_id: Optional[str] = None) -> None:
        """清除任务状态"""
        with self._lock:
            if task_id is None:
                self._status.clear()
            elif task_id in self._status:
                del self._status[task_id]


class ConcurrentFuturesTaskManager:
    """
    concurrent.futures 任务管理器封装
    
    实现与 FishAsyncTask 类似的任务管理接口，便于对比测试。
    """
    
    def __init__(self, max_workers: int = 10) -> None:
        """
        初始化任务管理器
        
        Args:
            max_workers: 最大工作线程数
        """
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.status_tracker = ConcurrentFuturesStatusTracker()
        self._task_counter = 0
        self._counter_lock = threading.Lock()
    
    def submit_task(
        self,
        func: Callable[..., Any],
        *args: Any,
        block: bool = False,
        timeout: Optional[float] = None,
        **kwargs: Any
    ) -> str:
        """
        提交任务
        
        Args:
            func: 任务函数
            *args: 位置参数
            block: 是否阻塞（concurrent.futures 不支持队列满，此参数忽略）
            timeout: 超时时间（concurrent.futures 不支持，此参数忽略）
            **kwargs: 关键字参数
        
        Returns:
            任务ID
        """
        task_id = str(uuid.uuid4())
        submit_time = time.time()
        
        # 设置任务状态为 pending
        self.status_tracker.set_pending(task_id, submit_time)
        
        # 提交任务
        def wrapped_func() -> Any:
            start_time = time.time()
            self.status_tracker.set_running(task_id, start_time)
            try:
                result = func(*args, **kwargs)
                end_time = time.time()
                self.status_tracker.set_completed(task_id, end_time, result)
                return result
            except Exception as e:
                end_time = time.time()
                self.status_tracker.set_failed(task_id, end_time, str(e))
                raise
        
        self.executor.submit(wrapped_func)
        return task_id
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        return self.status_tracker.get_status(task_id)
    
    def clear_task_status(self, task_id: Optional[str] = None) -> None:
        """清除任务状态"""
        self.status_tracker.clear(task_id)
    
    def shutdown(self) -> None:
        """关闭任务管理器"""
        self.executor.shutdown(wait=True)
        self.status_tracker.clear()
    
    def get_worker_count(self) -> int:
        """获取当前工作线程数"""
        return self.max_workers


class TestConcurrentFuturesComparison:
    """
    concurrent.futures 对比测试
    
    测试原生 Python 线程池的性能指标，与 FishAsyncTask 进行对比。
    """
    
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """每个测试前后的设置和清理"""
        cleanup_task_manager_instances()
        gc.collect()
        yield
        cleanup_task_manager_instances()
        gc.collect()
    
    @pytest.fixture
    def task_manager(self):
        """创建 concurrent.futures 任务管理器实例"""
        cpu_count = os.cpu_count() or 4
        max_workers = max(4, cpu_count * 2)
        manager = ConcurrentFuturesTaskManager(max_workers=max_workers)
        yield manager
        manager.shutdown()
    
    @pytest.fixture
    def fish_task_manager(self):
        """创建 FishAsyncTask 任务管理器实例"""
        cleanup_task_manager_instances()
        FishTaskManager._instances.clear()
        manager = FishTaskManager.__new__(FishTaskManager)
        manager._init_task_manager()
        yield manager
        try:
            manager.shutdown()
        except Exception:
            pass
        cleanup_task_manager_instances()
    
    def _get_memory_usage_mb(self) -> float:
        """获取当前进程的内存使用量（MB）"""
        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)
    
    def _get_cpu_usage_percent(self) -> float:
        """获取当前进程的 CPU 使用率"""
        process = psutil.Process()
        return process.cpu_percent()
    
    def test_task_submission_throughput(self, task_manager, fish_task_manager):
        """
        测试任务提交吞吐量
        
        对比 FishAsyncTask 和 concurrent.futures 的任务提交性能。
        
        测试步骤：
        1. 创建 5000 个快速任务（1ms）
        2. 使用 100 个并发线程提交任务
        3. 测量提交吞吐量和延迟
        
        预期结果：
        - FishAsyncTask: 提交吞吐量约 X tasks/s，P99 延迟约 Y ms
        - concurrent.futures: 提交吞吐量约 X tasks/s，P99 延迟约 Y ms
        """
        print_test_header(
            "concurrent.futures vs FishAsyncTask - 任务提交吞吐量",
            task_count=TestConfig.TASK_COUNT_MEDIUM,
            concurrent=TestConfig.CONCURRENT_THREADS_MEDIUM
        )
        
        def fast_task(value: int) -> int:
            time.sleep(0.001)
            return value * 2
        
        # 测试 FishAsyncTask
        print("\n--- FishAsyncTask 测试 ---")
        gc.collect()
        mem_before_fat = self._get_memory_usage_mb()
        cpu_before_fat = self._get_cpu_usage_percent()
        
        fish_metrics = PerformanceMetrics("FishAsyncTask - 任务提交")
        fish_metrics.start()
        
        fish_task_ids = []
        with ThreadPoolExecutor(max_workers=TestConfig.CONCURRENT_THREADS_MEDIUM) as executor:
            futures = []
            for i in range(TestConfig.TASK_COUNT_MEDIUM):
                future = executor.submit(
                    fish_task_manager.submit_task, fast_task, i, block=True, timeout=1.0
                )
                futures.append(future)
            
            for future in futures:
                try:
                    task_id = future.result()
                    fish_task_ids.append(task_id)
                    fish_metrics.record_success()
                except Exception as e:
                    fish_metrics.record_error(e)
        
        fish_metrics.stop()
        fish_time = fish_metrics.get_total_time()
        mem_after_fat = self._get_memory_usage_mb()
        cpu_after_fat = self._get_cpu_usage_percent()
        
        # 等待任务完成
        print("等待 FishAsyncTask 任务完成...")
        wait_for_all_tasks(fish_task_manager, fish_task_ids, timeout=120)
        
        print(f"\nFishAsyncTask 结果:")
        print(f"  总耗时: {fish_time:.3f}秒")
        print(f"  吞吐量: {TestConfig.TASK_COUNT_MEDIUM / fish_time:.0f} tasks/s")
        print(f"  QPS: {fish_metrics.get_qps():.0f}")
        print(f"  P99 延迟: {fish_metrics.get_percentile(99) * 1000:.3f}ms")
        print(f"  内存变化: {mem_before_fat:.1f}MB -> {mem_after_fat:.1f}MB")
        print(f"  CPU 使用率: {cpu_before_fat:.1f}% -> {cpu_after_fat:.1f}%")
        
        # 测试 concurrent.futures
        print("\n--- concurrent.futures 测试 ---")
        gc.collect()
        mem_before_cf = self._get_memory_usage_mb()
        cpu_before_cf = self._get_cpu_usage_percent()
        
        cf_metrics = PerformanceMetrics("concurrent.futures - 任务提交")
        cf_metrics.start()
        
        cf_task_ids = []
        with ThreadPoolExecutor(max_workers=TestConfig.CONCURRENT_THREADS_MEDIUM) as executor:
            futures = []
            for i in range(TestConfig.TASK_COUNT_MEDIUM):
                future = executor.submit(
                    task_manager.submit_task, fast_task, i, block=True, timeout=1.0
                )
                futures.append(future)
            
            for future in futures:
                try:
                    task_id = future.result()
                    cf_task_ids.append(task_id)
                    cf_metrics.record_success()
                except Exception as e:
                    cf_metrics.record_error(e)
        
        cf_metrics.stop()
        cf_time = cf_metrics.get_total_time()
        mem_after_cf = self._get_memory_usage_mb()
        cpu_after_cf = self._get_cpu_usage_percent()
        
        # 等待任务完成
        print("等待 concurrent.futures 任务完成...")
        time.sleep(5)  # 等待任务完成
        
        print(f"\nconcurrent.futures 结果:")
        print(f"  总耗时: {cf_time:.3f}秒")
        print(f"  吞吐量: {TestConfig.TASK_COUNT_MEDIUM / cf_time:.0f} tasks/s")
        print(f"  QPS: {cf_metrics.get_qps():.0f}")
        print(f"  P99 延迟: {cf_metrics.get_percentile(99) * 1000:.3f}ms")
        print(f"  内存变化: {mem_before_cf:.1f}MB -> {mem_after_cf:.1f}MB")
        print(f"  CPU 使用率: {cpu_before_cf:.1f}% -> {cpu_after_cf:.1f}%")
        
        # 打印对比结果
        print("\n" + "=" * 80)
        print("对比结果")
        print("=" * 80)
        fat_throughput = TestConfig.TASK_COUNT_MEDIUM / fish_time
        cf_throughput = TestConfig.TASK_COUNT_MEDIUM / cf_time
        
        print(f"\n{'指标':<25} {'FishAsyncTask':<20} {'concurrent.futures':<20}")
        print("-" * 65)
        print(f"{'吞吐量 (tasks/s)':<25} {fat_throughput:<20.0f} {cf_throughput:<20.0f}")
        print(f"{'P99 延迟 (ms)':<25} {fish_metrics.get_percentile(99) * 1000:<20.3f} {cf_metrics.get_percentile(99) * 1000:<20.3f}")
        print(f"{'平均延迟 (ms)':<25} {fish_metrics.get_avg_latency() * 1000:<20.3f} {cf_metrics.get_avg_latency() * 1000:<20.3f}")
        print(f"{'内存增量 (MB)':<25} {mem_after_fat - mem_before_fat:<20.1f} {mem_after_cf - mem_before_cf:<20.1f}")
        print(f"{'成功率 (%)':<25} {fish_metrics.get_success_rate() * 100:<19.1f}% {cf_metrics.get_success_rate() * 100:<19.1f}%")
        
        # 计算性能差异
        throughput_diff = ((fat_throughput - cf_throughput) / cf_throughput * 100) if cf_throughput > 0 else 0
        print(f"\n性能差异分析:")
        print(f"  吞吐量差异: {throughput_diff:+.1f}%")
        
        if fat_throughput > cf_throughput:
            print(f"  FishAsyncTask 吞吐量提升 {abs(throughput_diff):.1f}%")
        else:
            print(f"  concurrent.futures 吞吐量提升 {abs(throughput_diff):.1f}%")
        
        print_test_footer(max(fish_time, cf_time))
        
        return {
            "fish_async_task": fish_metrics.get_results(),
            "concurrent_futures": cf_metrics.get_results(),
        }
    
    def test_concurrent_status_query(self, task_manager, fish_task_manager):
        """
        测试并发状态查询性能
        
        对比 FishAsyncTask 和 concurrent.futures 的任务状态查询性能。
        
        测试步骤：
        1. 创建 10000 个已完成的任务
        2. 使用 200 个并发线程查询任务状态
        3. 测量查询吞吐量和延迟
        
        预期结果：
        - FishAsyncTask: 查询 QPS 约 X，P99 延迟约 Y ms
        - concurrent.futures: 查询 QPS 约 X，P99 延迟约 Y ms
        """
        print_test_header(
            "concurrent.futures vs FishAsyncTask - 并发状态查询",
            task_count=TestConfig.TASK_COUNT_LARGE,
            concurrent=TestConfig.CONCURRENT_THREADS_LARGE
        )
        
        def fast_task(value: int) -> int:
            time.sleep(0.001)
            return value * 2
        
        # 创建 FishAsyncTask 任务
        print("\n--- 创建 FishAsyncTask 任务 ---")
        FishTaskManager._instances.clear()
        fish_manager = FishTaskManager.__new__(FishTaskManager)
        fish_manager._init_task_manager()
        
        fish_task_ids = []
        for i in range(TestConfig.TASK_COUNT_LARGE):
            task_id = fish_manager.submit_task(fast_task, i, block=True, timeout=1.0)
            fish_task_ids.append(task_id)
        
        # 等待所有任务完成
        print("等待 FishAsyncTask 任务完成...")
        wait_success = wait_for_all_tasks(fish_manager, fish_task_ids, timeout=120)
        assert wait_success, "部分 FishAsyncTask 任务未完成"
        print(f"FishAsyncTask 任务创建完成: {len(fish_task_ids)} 个")
        
        # 创建 concurrent.futures 任务
        print("\n--- 创建 concurrent.futures 任务 ---")
        cf_manager = ConcurrentFuturesTaskManager(max_workers=100)
        
        cf_task_ids = []
        for i in range(TestConfig.TASK_COUNT_LARGE):
            task_id = cf_manager.submit_task(fast_task, i, block=True, timeout=1.0)
            cf_task_ids.append(task_id)
        
        # 等待任务完成
        time.sleep(5)
        print(f"concurrent.futures 任务创建完成: {len(cf_task_ids)} 个")
        
        # 测试 FishAsyncTask 状态查询
        print("\n--- FishAsyncTask 状态查询测试 ---")
        gc.collect()
        
        fish_metrics = PerformanceMetrics("FishAsyncTask - 状态查询")
        fish_metrics.start()
        
        with ThreadPoolExecutor(max_workers=TestConfig.CONCURRENT_THREADS_LARGE) as executor:
            futures = []
            for tid in fish_task_ids:
                future = executor.submit(fish_manager.get_task_status, tid)
                futures.append((time.perf_counter(), future))
            
            for start_time, future in futures:
                try:
                    result = future.result()
                    end_time = time.perf_counter()
                    latency = end_time - start_time
                    fish_metrics.record_latency(latency)
                    fish_metrics.record_success()
                except Exception as e:
                    fish_metrics.record_error(e)
        
        fish_metrics.stop()
        
        print(f"\nFishAsyncTask 状态查询结果:")
        print(f"  总查询数: {fish_metrics.get_total_operations()}")
        print(f"  QPS: {fish_metrics.get_qps():.0f}")
        print(f"  P99 延迟: {fish_metrics.get_percentile(99) * 1000:.3f}ms")
        print(f"  P50 延迟: {fish_metrics.get_percentile(50) * 1000:.3f}ms")
        
        # 测试 concurrent.futures 状态查询
        print("\n--- concurrent.futures 状态查询测试 ---")
        gc.collect()
        
        cf_metrics = PerformanceMetrics("concurrent.futures - 状态查询")
        cf_metrics.start()
        
        with ThreadPoolExecutor(max_workers=TestConfig.CONCURRENT_THREADS_LARGE) as executor:
            futures = []
            for tid in cf_task_ids:
                future = executor.submit(cf_manager.get_task_status, tid)
                futures.append((time.perf_counter(), future))
            
            for start_time, future in futures:
                try:
                    result = future.result()
                    end_time = time.perf_counter()
                    latency = end_time - start_time
                    cf_metrics.record_latency(latency)
                    cf_metrics.record_success()
                except Exception as e:
                    cf_metrics.record_error(e)
        
        cf_metrics.stop()
        
        print(f"\nconcurrent.futures 状态查询结果:")
        print(f"  总查询数: {cf_metrics.get_total_operations()}")
        print(f"  QPS: {cf_metrics.get_qps():.0f}")
        print(f"  P99 延迟: {cf_metrics.get_percentile(99) * 1000:.3f}ms")
        print(f"  P50 延迟: {cf_metrics.get_percentile(50) * 1000:.3f}ms")
        
        # 打印对比结果
        print("\n" + "=" * 80)
        print("对比结果")
        print("=" * 80)
        
        print(f"\n{'指标':<25} {'FishAsyncTask':<20} {'concurrent.futures':<20}")
        print("-" * 65)
        print(f"{'QPS':<25} {fish_metrics.get_qps():<20.0f} {cf_metrics.get_qps():<20.0f}")
        print(f"{'P99 延迟 (ms)':<25} {fish_metrics.get_percentile(99) * 1000:<20.3f} {cf_metrics.get_percentile(99) * 1000:<20.3f}")
        print(f"{'P50 延迟 (ms)':<25} {fish_metrics.get_percentile(50) * 1000:<20.3f} {cf_metrics.get_percentile(50) * 1000:<20.3f}")
        print(f"{'平均延迟 (ms)':<25} {fish_metrics.get_avg_latency() * 1000:<20.3f} {cf_metrics.get_avg_latency() * 1000:<20.3f}")
        print(f"{'成功率 (%)':<25} {fish_metrics.get_success_rate() * 100:<19.1f}% {cf_metrics.get_success_rate() * 100:<19.1f}%")
        
        # 计算性能差异
        qps_diff = ((fish_metrics.get_qps() - cf_metrics.get_qps()) / cf_metrics.get_qps() * 100) if cf_metrics.get_qps() > 0 else 0
        print(f"\n性能差异分析:")
        print(f"  QPS 差异: {qps_diff:+.1f}%")
        
        if qps_diff > 0:
            print(f"  FishAsyncTask QPS 提升 {qps_diff:.1f}%")
        else:
            print(f"  concurrent.futures QPS 提升 {abs(qps_diff):.1f}%")
        
        print_test_footer(fish_metrics.get_total_time() + cf_metrics.get_total_time())
        
        # 清理
        cf_manager.shutdown()
        fish_manager.shutdown()
        
        return {
            "fish_async_task": fish_metrics.get_results(),
            "concurrent_futures": cf_metrics.get_results(),
        }
    
    def test_task_execution_time(self, task_manager, fish_task_manager):
        """
        测试任务执行时间
        
        对比 FishAsyncTask 和 concurrent.futures 执行相同任务的耗时。
        
        测试步骤：
        1. 创建 1000 个耗时任务（10ms）
        2. 测量任务总执行时间
        3. 计算实际吞吐量
        
        预期结果：
        - FishAsyncTask: 执行时间约 X 秒，吞吐量约 Y tasks/s
        - concurrent.futures: 执行时间约 X 秒，吞吐量约 Y tasks/s
        """
        print_test_header(
            "concurrent.futures vs FishAsyncTask - 任务执行时间",
            task_count=TestConfig.TASK_COUNT_SMALL,
            concurrent=50
        )
        
        def normal_task(value: int) -> int:
            time.sleep(0.01)  # 10ms 任务
            return value * 2
        
        # 测试 FishAsyncTask
        print("\n--- FishAsyncTask 测试 ---")
        FishTaskManager._instances.clear()
        fish_manager = FishTaskManager.__new__(FishTaskManager)
        fish_manager._init_task_manager()
        
        gc.collect()
        
        fish_start = time.perf_counter()
        fish_task_ids = create_test_tasks(fish_manager, TestConfig.TASK_COUNT_SMALL, normal_task)
        print(f"已提交 {len(fish_task_ids)} 个任务")
        
        fish_execution_start = time.perf_counter()
        wait_success = wait_for_all_tasks(fish_manager, fish_task_ids, timeout=120)
        fish_execution_time = time.perf_counter() - fish_execution_start
        fish_total_time = time.perf_counter() - fish_start
        
        assert wait_success, "部分 FishAsyncTask 任务未完成"
        
        fish_throughput = len(fish_task_ids) / fish_execution_time
        
        print(f"\nFishAsyncTask 执行结果:")
        print(f"  提交时间: {fish_execution_start - fish_start:.3f}秒")
        print(f"  执行时间: {fish_execution_time:.3f}秒")
        print(f"  总耗时: {fish_total_time:.3f}秒")
        print(f"  吞吐量: {fish_throughput:.0f} tasks/s")
        
        # 测试 concurrent.futures
        print("\n--- concurrent.futures 测试 ---")
        gc.collect()
        
        cf_manager = ConcurrentFuturesTaskManager(max_workers=50)
        
        cf_start = time.perf_counter()
        cf_task_ids = []
        for i in range(TestConfig.TASK_COUNT_SMALL):
            task_id = cf_manager.submit_task(normal_task, i, block=True, timeout=1.0)
            cf_task_ids.append(task_id)
        
        cf_execution_start = time.perf_counter()
        # 等待任务完成
        time.sleep(20)  # 10ms * 1000 / 50 = 200ms 理论最小值，实际需要等待
        cf_execution_time = time.perf_counter() - cf_execution_start
        cf_total_time = time.perf_counter() - cf_start
        
        cf_throughput = len(cf_task_ids) / cf_execution_time
        
        print(f"\nconcurrent.futures 执行结果:")
        print(f"  提交时间: {cf_execution_start - cf_start:.3f}秒")
        print(f"  执行时间: {cf_execution_time:.3f}秒")
        print(f"  总耗时: {cf_total_time:.3f}秒")
        print(f"  吞吐量: {cf_throughput:.0f} tasks/s")
        
        # 打印对比结果
        print("\n" + "=" * 80)
        print("对比结果")
        print("=" * 80)
        
        print(f"\n{'指标':<25} {'FishAsyncTask':<20} {'concurrent.futures':<20}")
        print("-" * 65)
        print(f"{'执行时间 (秒)':<25} {fish_execution_time:<20.3f} {cf_execution_time:<20.3f}")
        print(f"{'吞吐量 (tasks/s)':<25} {fish_throughput:<20.0f} {cf_throughput:<20.0f}")
        print(f"{'总耗时 (秒)':<25} {fish_total_time:<20.3f} {cf_total_time:<20.3f}")
        
        print_test_footer(max(fish_total_time, cf_total_time))
        
        # 清理
        cf_manager.shutdown()
        fish_manager.shutdown()
        
        return {
            "fish_async_task": {
                "execution_time": fish_execution_time,
                "throughput": fish_throughput,
                "total_time": fish_total_time,
            },
            "concurrent_futures": {
                "execution_time": cf_execution_time,
                "throughput": cf_throughput,
                "total_time": cf_total_time,
            },
        }
    
    def test_end_to_end_performance(self, task_manager, fish_task_manager):
        """
        端到端性能测试
        
        模拟真实业务场景，测试完整的任务处理流程。
        
        测试步骤：
        1. 提交 5000 个任务（10ms 耗时）
        2. 等待任务执行完成
        3. 并发查询所有任务状态
        4. 测量整体性能指标
        
        预期结果：
        - FishAsyncTask: 端到端时间约 X 秒，状态查询 QPS 约 Y
        - concurrent.futures: 端到端时间约 X 秒，状态查询 QPS 约 Y
        """
        print_test_header(
            "concurrent.futures vs FishAsyncTask - 端到端性能",
            task_count=TestConfig.TASK_COUNT_MEDIUM
        )
        
        def normal_task(value: int) -> int:
            time.sleep(0.01)
            return value * 2
        
        # 测试 FishAsyncTask
        print("\n--- FishAsyncTask 测试 ---")
        FishTaskManager._instances.clear()
        fish_manager = FishTaskManager.__new__(FishTaskManager)
        fish_manager._init_task_manager()
        
        gc.collect()
        
        # 提交任务
        print("提交 FishAsyncTask 任务...")
        fish_start = time.perf_counter()
        fish_task_ids = create_test_tasks(fish_manager, TestConfig.TASK_COUNT_MEDIUM, normal_task)
        print(f"已提交 {len(fish_task_ids)} 个任务")
        
        # 等待任务执行
        print("等待 FishAsyncTask 任务执行...")
        fish_execution_start = time.perf_counter()
        wait_success = wait_for_all_tasks(fish_manager, fish_task_ids, timeout=180)
        fish_execution_time = time.perf_counter() - fish_execution_start
        
        assert wait_success, "部分 FishAsyncTask 任务未完成"
        
        # 并发查询状态
        print("FishAsyncTask 并发查询任务状态...")
        fish_query_metrics = PerformanceMetrics("FishAsyncTask - 端到端状态查询")
        fish_query_metrics.start()
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = []
            for tid in fish_task_ids:
                future = executor.submit(fish_manager.get_task_status, tid)
                futures.append((time.perf_counter(), future))
            
            for start_time, future in futures:
                try:
                    result = future.result()
                    end_time = time.perf_counter()
                    latency = end_time - start_time
                    fish_query_metrics.record_latency(latency)
                    fish_query_metrics.record_success()
                except Exception as e:
                    fish_query_metrics.record_error(e)
        
        fish_query_metrics.stop()
        fish_total_time = time.perf_counter() - fish_start
        
        print(f"\nFishAsyncTask 端到端结果:")
        print(f"  任务执行时间: {fish_execution_time:.3f}秒")
        print(f"  总耗时: {fish_total_time:.3f}秒")
        print(f"  任务吞吐量: {len(fish_task_ids) / fish_execution_time:.0f} tasks/s")
        print(f"  状态查询 QPS: {fish_query_metrics.get_qps():.0f}")
        print(f"  状态查询 P99 延迟: {fish_query_metrics.get_percentile(99) * 1000:.3f}ms")
        
        # 测试 concurrent.futures
        print("\n--- concurrent.futures 测试 ---")
        gc.collect()
        
        cf_manager = ConcurrentFuturesTaskManager(max_workers=50)
        
        # 提交任务
        print("提交 concurrent.futures 任务...")
        cf_start = time.perf_counter()
        cf_task_ids = []
        for i in range(TestConfig.TASK_COUNT_MEDIUM):
            task_id = cf_manager.submit_task(normal_task, i, block=True, timeout=1.0)
            cf_task_ids.append(task_id)
        print(f"已提交 {len(cf_task_ids)} 个任务")
        
        # 等待任务执行
        print("等待 concurrent.futures 任务执行...")
        cf_execution_start = time.perf_counter()
        time.sleep(25)  # 等待任务完成
        cf_execution_time = time.perf_counter() - cf_execution_start
        
        # 并发查询状态
        print("concurrent.futures 并发查询任务状态...")
        cf_query_metrics = PerformanceMetrics("concurrent.futures - 端到端状态查询")
        cf_query_metrics.start()
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = []
            for tid in cf_task_ids:
                future = executor.submit(cf_manager.get_task_status, tid)
                futures.append((time.perf_counter(), future))
            
            for start_time, future in futures:
                try:
                    result = future.result()
                    end_time = time.perf_counter()
                    latency = end_time - start_time
                    cf_query_metrics.record_latency(latency)
                    cf_query_metrics.record_success()
                except Exception as e:
                    cf_query_metrics.record_error(e)
        
        cf_query_metrics.stop()
        cf_total_time = time.perf_counter() - cf_start
        
        print(f"\nconcurrent.futures 端到端结果:")
        print(f"  任务执行时间: {cf_execution_time:.3f}秒")
        print(f"  总耗时: {cf_total_time:.3f}秒")
        print(f"  任务吞吐量: {len(cf_task_ids) / cf_execution_time:.0f} tasks/s")
        print(f"  状态查询 QPS: {cf_query_metrics.get_qps():.0f}")
        print(f"  状态查询 P99 延迟: {cf_query_metrics.get_percentile(99) * 1000:.3f}ms")
        
        # 打印对比结果
        print("\n" + "=" * 80)
        print("端到端对比结果")
        print("=" * 80)
        
        print(f"\n{'指标':<25} {'FishAsyncTask':<20} {'concurrent.futures':<20}")
        print("-" * 65)
        print(f"{'任务执行时间 (秒)':<25} {fish_execution_time:<20.3f} {cf_execution_time:<20.3f}")
        print(f"{'总耗时 (秒)':<25} {fish_total_time:<20.3f} {cf_total_time:<20.3f}")
        print(f"{'任务吞吐量 (tasks/s)':<25} {len(fish_task_ids) / fish_execution_time:<20.0f} {len(cf_task_ids) / cf_execution_time:<20.0f}")
        print(f"{'状态查询 QPS':<25} {fish_query_metrics.get_qps():<20.0f} {cf_query_metrics.get_qps():<20.0f}")
        print(f"{'状态查询 P99 (ms)':<25} {fish_query_metrics.get_percentile(99) * 1000:<20.3f} {cf_query_metrics.get_percentile(99) * 1000:<20.3f}")
        
        print_test_footer(max(fish_total_time, cf_total_time))
        
        # 清理
        cf_manager.shutdown()
        fish_manager.shutdown()
        
        return {
            "fish_async_task": {
                "execution_time": fish_execution_time,
                "total_time": fish_total_time,
                "throughput": len(fish_task_ids) / fish_execution_time,
                "query_qps": fish_query_metrics.get_qps(),
                "query_p99_ms": fish_query_metrics.get_percentile(99) * 1000,
            },
            "concurrent_futures": {
                "execution_time": cf_execution_time,
                "total_time": cf_total_time,
                "throughput": len(cf_task_ids) / cf_execution_time,
                "query_qps": cf_query_metrics.get_qps(),
                "query_p99_ms": cf_query_metrics.get_percentile(99) * 1000,
            },
        }


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

