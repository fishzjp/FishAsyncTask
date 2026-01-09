"""
PyPI 版本基准性能测试

测试 fish-async-task 发布版本的性能指标。
此测试用于与开发版本进行对比，验证优化效果。

注意：此测试需要在纯净的 PyPI 版本环境中运行。
"""

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import pytest

from tests.performance.conftest import (
    TestConfig,
    cleanup_task_manager_instances,
    create_test_tasks,
    print_test_footer,
    print_test_header,
    wait_for_all_tasks,
    wait_for_task_completion,
)
from tests.performance.utils import PerformanceMetrics, ThroughputTracker


class TestPyPIBaselinePerformance:
    """
    PyPI 版本性能基准测试
    
    测试发布版本的各项性能指标，为开发版本对比提供基准数据。
    """
    
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """每个测试前后的设置和清理"""
        cleanup_task_manager_instances()
        yield
        cleanup_task_manager_instances()
    
    @pytest.fixture
    def task_manager(self):
        """创建任务管理器实例"""
        from fish_async_task.task_manager import TaskManager as TaskManagerClass
        manager = TaskManagerClass.__new__(TaskManagerClass)
        manager._init_task_manager()
        yield manager
        try:
            manager.shutdown()
        except Exception:
            pass
    
    def test_concurrent_status_query_baseline(self, task_manager):
        """
        测试并发状态查询性能
        
        这是最核心的性能测试场景，测量在高并发下查询任务状态的能力。
        """
        from fish_async_task.task_manager import TaskManager as TaskManagerClass
        
        print_test_header(
            "PyPI版本 - 并发状态查询性能",
            task_count=TestConfig.TASK_COUNT_LARGE,
            concurrent=TestConfig.CONCURRENT_THREADS_LARGE
        )
        
        # 创建快速任务用于测试
        def fast_task(value: int) -> int:
            time.sleep(0.001)  # 1ms
            return value * 2
        
        # 清理单例
        TaskManagerClass._instances.clear()
        manager = TaskManagerClass.__new__(TaskManagerClass)
        manager._init_task_manager()
        
        # 创建大量已完成的任务
        task_ids = []
        print("创建测试任务...")
        start_time = time.perf_counter()
        
        for i in range(TestConfig.TASK_COUNT_LARGE):
            task_id = manager.submit_task(fast_task, i, block=True, timeout=1.0)
            task_ids.append(task_id)
        
        create_time = time.perf_counter() - start_time
        print(f"创建 {len(task_ids)} 个任务耗时: {create_time:.3f}秒")
        
        # 等待所有任务完成
        print("等待任务完成...")
        wait_success = wait_for_all_tasks(manager, task_ids, timeout=TestConfig.TEST_TIMEOUT)
        assert wait_success, "部分任务未在超时时间内完成"
        
        # 并发查询性能测试
        print("执行并发查询测试...")
        metrics = PerformanceMetrics("PyPI版本 - 状态查询")
        metrics.start()

        with ThreadPoolExecutor(max_workers=TestConfig.CONCURRENT_THREADS_LARGE) as executor:
            futures = []
            for tid in task_ids:
                future = executor.submit(manager.get_task_status, tid)
                futures.append((time.perf_counter(), future))

            for start_time, future in futures:
                try:
                    result = future.result()
                    end_time = time.perf_counter()
                    latency = end_time - start_time
                    metrics.record_latency(latency)
                    metrics.record_success()
                except Exception as e:
                    metrics.record_error(e)

        metrics.stop()
        
        # 验证结果
        assert len(futures) == len(task_ids), "查询结果数量不匹配"
        assert all(r is not None for r in [f.result() for _, f in futures]), "存在 None 结果"
        
        elapsed_time = metrics.get_total_time()
        metrics.print_results()
        print_test_footer(elapsed_time)
        
        # 保存结果用于对比
        baseline_results = metrics.get_results()
        print("\n基准测试结果 (PyPI版本):")
        print(f"  QPS: {baseline_results['qps']:.0f}")
        print(f"  P99延迟: {baseline_results['latency_stats_ms']['p99']:.3f}ms")
        
        # 返回结果供后续对比
        return baseline_results
    
    def test_cleanup_performance_baseline(self, task_manager):
        """
        测试清理操作性能
        
        测量清理大量过期任务状态所需的时间。
        """
        from fish_async_task.task_manager import TaskManager as TaskManagerClass
        
        print_test_header(
            "PyPI版本 - 清理操作性能",
            task_count=TestConfig.TASK_COUNT_LARGE
        )
        
        def fast_task(value: int) -> int:
            time.sleep(0.001)
            return value * 2
        
        # 清理单例并创建新实例
        TaskManagerClass._instances.clear()
        manager = TaskManagerClass.__new__(TaskManagerClass)
        manager._init_task_manager()
        
        # 创建大量已完成的任务（使用短 TTL）
        task_ids = []
        print("创建测试任务...")
        original_ttl = manager.task_status_ttl
        
        for i in range(TestConfig.TASK_COUNT_LARGE):
            task_id = manager.submit_task(fast_task, i, block=True, timeout=1.0)
            task_ids.append(task_id)
        
        # 等待所有任务完成
        wait_success = wait_for_all_tasks(manager, task_ids, timeout=60)
        assert wait_success, "任务未完成"
        
        # 设置短 TTL 使任务过期
        manager.task_status_ttl = 1
        manager.status_manager.task_status_ttl = 1
        manager.status_manager.sharded_status.ttl = 1
        
        print("等待任务过期...")
        time.sleep(2)  # 等待 TTL 过期
        
        # 执行清理
        print("执行清理操作...")
        start_time = time.perf_counter()
        cleaned_count = manager.status_manager.cleanup_old_task_status()
        cleanup_time = time.perf_counter() - start_time
        
        print(f"\n清理测试结果:")
        print(f"  清理任务数: {cleaned_count}")
        print(f"  清理耗时: {cleanup_time * 1000:.3f}ms")
        print(f"  清理吞吐量: {cleaned_count / cleanup_time:.0f} tasks/s")
        
        # 恢复 TTL
        manager.task_status_ttl = original_ttl
        
        print_test_footer(cleanup_time)
        
        return {
            "cleanup_count": cleaned_count,
            "cleanup_time_ms": cleanup_time * 1000,
            "throughput": cleaned_count / cleanup_time if cleanup_time > 0 else 0,
        }
    
    def test_task_submission_throughput_baseline(self, task_manager):
        """
        测试任务提交吞吐量
        
        测量在高并发下提交任务的能力。
        """
        from fish_async_task.task_manager import TaskManager as TaskManagerClass
        
        print_test_header(
            "PyPI版本 - 任务提交吞吐量",
            task_count=TestConfig.TASK_COUNT_MEDIUM,
            concurrent=TestConfig.CONCURRENT_THREADS_MEDIUM
        )
        
        def fast_task(value: int) -> int:
            time.sleep(0.001)
            return value * 2
        
        # 清理单例
        TaskManagerClass._instances.clear()
        manager = TaskManagerClass.__new__(TaskManagerClass)
        manager._init_task_manager()
        
        # 并发提交任务
        print("并发提交任务...")
        metrics = PerformanceMetrics("任务提交")
        metrics.start()
        
        task_ids = []
        with ThreadPoolExecutor(max_workers=TestConfig.CONCURRENT_THREADS_MEDIUM) as executor:
            futures = []
            for i in range(TestConfig.TASK_COUNT_MEDIUM):
                future = executor.submit(
                    manager.submit_task, fast_task, i, block=True, timeout=1.0
                )
                futures.append(future)
            
            for future in futures:
                try:
                    task_id = future.result()
                    task_ids.append(task_id)
                    metrics.record_success()
                except Exception as e:
                    metrics.record_error(e)
        
        metrics.stop()
        elapsed_time = metrics.get_total_time()
        
        # 等待所有任务完成
        print(f"等待 {len(task_ids)} 个任务完成...")
        wait_for_all_tasks(manager, task_ids, timeout=60)
        
        metrics.print_results()
        print_test_footer(elapsed_time)
        
        return metrics.get_results()
    
    def test_end_to_end_performance_baseline(self, task_manager):
        """
        端到端性能测试
        
        模拟真实业务场景，测试完整的任务处理流程。
        """
        from fish_async_task.task_manager import TaskManager as TaskManagerClass
        
        print_test_header(
            "PyPI版本 - 端到端性能测试",
            task_count=TestConfig.TASK_COUNT_MEDIUM
        )
        
        def normal_task(value: int) -> int:
            time.sleep(0.01)  # 10ms 任务
            return value * 2
        
        # 清理单例
        TaskManagerClass._instances.clear()
        manager = TaskManagerClass.__new__(TaskManagerClass)
        manager._init_task_manager()
        
        # 提交任务
        print("提交任务...")
        task_ids = create_test_tasks(manager, TestConfig.TASK_COUNT_MEDIUM, normal_task)
        print(f"已提交 {len(task_ids)} 个任务")
        
        # 测量任务执行时间
        print("等待任务执行...")
        execution_start = time.perf_counter()
        wait_success = wait_for_all_tasks(manager, task_ids, timeout=120)
        execution_time = time.perf_counter() - execution_start
        
        # 并发查询状态（模拟监控场景）
        print("并发查询任务状态...")
        query_metrics = PerformanceMetrics("端到端状态查询")
        query_metrics.start()

        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = []
            for tid in task_ids:
                future = executor.submit(manager.get_task_status, tid)
                futures.append((time.perf_counter(), future))

            for start_time, future in futures:
                try:
                    result = future.result()
                    end_time = time.perf_counter()
                    latency = end_time - start_time
                    query_metrics.record_latency(latency)
                    query_metrics.record_success()
                except Exception as e:
                    query_metrics.record_error(e)

        query_metrics.stop()

        # 验证结果
        assert len(futures) == len(task_ids)
        
        print(f"\n端到端测试结果:")
        print(f"  任务执行时间: {execution_time:.3f}秒")
        print(f"  任务吞吐量: {len(task_ids) / execution_time:.0f} tasks/s")
        print(f"  状态查询 QPS: {query_metrics.get_qps():.0f}")
        print(f"  状态查询 P99延迟: {query_metrics.get_percentile(99) * 1000:.3f}ms")
        
        query_metrics.print_results()
        print_test_footer(execution_time)
        
        return {
            "execution_time": execution_time,
            "throughput": len(task_ids) / execution_time,
            "query_qps": query_metrics.get_qps(),
            "query_p99_ms": query_metrics.get_percentile(99) * 1000,
        }


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

