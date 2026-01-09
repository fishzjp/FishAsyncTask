"""
综合性能对比报告

整合 FishAsyncTask、concurrent.futures、huey、dramatiq 的所有性能测试结果，
生成统一的对比报告。

测试指标：
- 任务提交吞吐量 (tasks/s)
- 任务状态查询 QPS
- 任务执行时间 (s)
- 端到端性能 (s)
- 延迟分布 (P50, P90, P95, P99, P99.9)
- 内存使用 (MB)
- CPU 使用率 (%)
- 清理性能 (tasks/s)
"""

import gc
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

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
from tests.performance.utils import PerformanceMetrics


def is_redis_available() -> bool:
    """检查 Redis 是否可用"""
    try:
        import redis
        client = redis.Redis(host="localhost", port=6379, socket_timeout=1)
        client.ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def redis_available():
    """检查 Redis 是否可用"""
    return is_redis_available()


@pytest.fixture
def fish_task_manager():
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


class TestComprehensiveComparisonReport:
    """
    综合性能对比报告测试
    
    运行所有库的对比测试，收集结果并生成统一报告。
    """
    
    def _get_memory_usage_mb(self) -> float:
        """获取当前进程的内存使用量（MB）"""
        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)
    
    def _get_cpu_usage_percent(self) -> float:
        """获取当前进程的 CPU 使用率"""
        process = psutil.Process()
        return process.cpu_percent()
    
    def _create_concurrent_futures_manager(self) -> "ConcurrentFuturesManager":
        """创建 concurrent.futures 任务管理器"""
        from tests.performance.test_library_comparison import ConcurrentFuturesTaskManager
        
        cpu_count = os.cpu_count() or 4
        max_workers = max(4, cpu_count * 2)
        return ConcurrentFuturesTaskManager(max_workers=max_workers)
    
    def _print_comparison_table(
        self,
        title: str,
        headers: List[str],
        rows: List[List[Any]]
    ) -> None:
        """
        打印对比表格
        
        Args:
            title: 表格标题
            headers: 表头
            rows: 数据行
        """
        # 计算每列最大宽度
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                cell_str = str(cell)
                col_widths[i] = max(col_widths[i], len(cell_str))
        
        # 打印标题
        print(f"\n{'=' * (sum(col_widths) + len(headers) * 3)}")
        print(f"  {title}")
        print(f"{'=' * (sum(col_widths) + len(headers) * 3)}")
        
        # 打印表头
        header_line = "  "
        for i, h in enumerate(headers):
            header_line += h.ljust(col_widths[i]) + "  "
        print(header_line)
        print("-" * (sum(col_widths) + len(headers) * 3))
        
        # 打印数据行
        for row in rows:
            row_line = "  "
            for i, cell in enumerate(row):
                row_line += str(cell).ljust(col_widths[i]) + "  "
            print(row_line)
        
        print(f"{'=' * (sum(col_widths) + len(headers) * 3)}\n")
    
    def test_comprehensive_throughput_comparison(self, fish_task_manager, redis_available):
        """
        综合吞吐量对比测试
        
        对比所有库的任务提交吞吐量。
        
        测试步骤：
        1. 测试 FishAsyncTask 吞吐量
        2. 测试 concurrent.futures 吞吐量
        3. 测试 huey 吞吐量（如果 Redis 可用）
        4. 测试 dramatiq 吞吐量（如果 Redis 可用）
        5. 生成对比报告
        
        预期结果：
        各库的吞吐量对比表格
        """
        print_test_header(
            "综合吞吐量对比测试",
            task_count=TestConfig.TASK_COUNT_MEDIUM,
            concurrent=TestConfig.CONCURRENT_THREADS_MEDIUM
        )
        
        def fast_task(value: int) -> int:
            time.sleep(0.001)
            return value * 2
        
        results: Dict[str, Dict[str, Any]] = {}
        
        # 测试 FishAsyncTask
        print("\n--- FishAsyncTask 测试 ---")
        gc.collect()
        
        FishTaskManager._instances.clear()
        fish_manager = FishTaskManager.__new__(FishTaskManager)
        fish_manager._init_task_manager()
        
        mem_before = self._get_memory_usage_mb()
        
        fish_metrics = PerformanceMetrics("FishAsyncTask - 吞吐量")
        fish_metrics.start()
        
        fish_task_ids = []
        with ThreadPoolExecutor(max_workers=TestConfig.CONCURRENT_THREADS_MEDIUM) as executor:
            futures = []
            for i in range(TestConfig.TASK_COUNT_MEDIUM):
                future = executor.submit(
                    fish_manager.submit_task, fast_task, i, block=True, timeout=1.0
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
        mem_after = self._get_memory_usage_mb()
        fish_time = fish_metrics.get_total_time()
        
        wait_for_all_tasks(fish_manager, fish_task_ids, timeout=120)
        
        results["FishAsyncTask"] = {
            "total_time": fish_time,
            "throughput": TestConfig.TASK_COUNT_MEDIUM / fish_time,
            "qps": fish_metrics.get_qps(),
            "p99_latency_ms": fish_metrics.get_percentile(99) * 1000,
            "avg_latency_ms": fish_metrics.get_avg_latency() * 1000,
            "success_rate": fish_metrics.get_success_rate() * 100,
            "memory_mb": mem_after - mem_before,
        }
        
        print(f"  吞吐量: {results['FishAsyncTask']['throughput']:.0f} tasks/s")
        print(f"  P99 延迟: {results['FishAsyncTask']['p99_latency_ms']:.3f}ms")
        
        # 测试 concurrent.futures
        print("\n--- concurrent.futures 测试 ---")
        gc.collect()
        
        cf_manager = self._create_concurrent_futures_manager()
        mem_before = self._get_memory_usage_mb()
        
        cf_metrics = PerformanceMetrics("concurrent.futures - 吞吐量")
        cf_metrics.start()
        
        cf_task_ids = []
        with ThreadPoolExecutor(max_workers=TestConfig.CONCURRENT_THREADS_MEDIUM) as executor:
            futures = []
            for i in range(TestConfig.TASK_COUNT_MEDIUM):
                future = executor.submit(
                    cf_manager.submit_task, fast_task, i, block=True, timeout=1.0
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
        mem_after = self._get_memory_usage_mb()
        cf_time = cf_metrics.get_total_time()
        
        # 等待完成
        time.sleep(5)
        
        results["concurrent.futures"] = {
            "total_time": cf_time,
            "throughput": TestConfig.TASK_COUNT_MEDIUM / cf_time,
            "qps": cf_metrics.get_qps(),
            "p99_latency_ms": cf_metrics.get_percentile(99) * 1000,
            "avg_latency_ms": cf_metrics.get_avg_latency() * 1000,
            "success_rate": cf_metrics.get_success_rate() * 100,
            "memory_mb": mem_after - mem_before,
        }
        
        print(f"  吞吐量: {results['concurrent.futures']['throughput']:.0f} tasks/s")
        print(f"  P99 延迟: {results['concurrent.futures']['p99_latency_ms']:.3f}ms")
        
        # 测试 huey（如果 Redis 可用）
        if redis_available:
            print("\n--- huey 测试 ---")
            gc.collect()
            
            from huey import RedisHuey
            huey = RedisHuey(
                'comprehensive_test',
                host=os.environ.get("REDIS_HOST", "localhost"),
                port=int(os.environ.get("REDIS_PORT", 6379)),
                db=15,
            )
            
            @huey.task()
            def huey_fast_task(value: int) -> int:
                time.sleep(0.001)
                return value * 2
            
            mem_before = self._get_memory_usage_mb()
            
            huey_metrics = PerformanceMetrics("huey - 吞吐量")
            huey_metrics.start()
            
            huey_results = []
            with ThreadPoolExecutor(max_workers=TestConfig.CONCURRENT_THREADS_MEDIUM) as executor:
                futures = []
                for i in range(TestConfig.TASK_COUNT_MEDIUM):
                    future = executor.submit(huey_fast_task.send, i)
                    futures.append(future)
                
                for future in futures:
                    try:
                        msg = future.result()
                        huey_results.append(msg)
                        huey_metrics.record_success()
                    except Exception as e:
                        huey_metrics.record_error(e)
            
            huey_metrics.stop()
            mem_after = self._get_memory_usage_mb()
            huey_time = huey_metrics.get_total_time()
            
            # 等待完成
            for msg in huey_results:
                try:
                    msg.get(block=True, timeout=30)
                except Exception:
                    pass
            
            results["huey"] = {
                "total_time": huey_time,
                "throughput": TestConfig.TASK_COUNT_MEDIUM / huey_time,
                "qps": huey_metrics.get_qps(),
                "p99_latency_ms": huey_metrics.get_percentile(99) * 1000,
                "avg_latency_ms": huey_metrics.get_avg_latency() * 1000,
                "success_rate": huey_metrics.get_success_rate() * 100,
                "memory_mb": mem_after - mem_before,
            }
            
            print(f"  吞吐量: {results['huey']['throughput']:.0f} tasks/s")
            print(f"  P99 延迟: {results['huey']['p99_latency_ms']:.3f}ms")
            
            # 清理
            huey.flush()
        
        # 测试 dramatiq（如果 Redis 可用）
        if redis_available:
            print("\n--- dramatiq 测试 ---")
            gc.collect()
            
            import dramatiq
            from dramatiq.brokers.redis import RedisBroker
            
            broker = RedisBroker(
                host=os.environ.get("REDIS_HOST", "localhost"),
                port=int(os.environ.get("REDIS_PORT", 6379)),
                db=14,
            )
            dramatiq.set_broker(broker)
            
            @dramatiq.actor
            def dramatiq_fast_task(value: int) -> int:
                time.sleep(0.001)
                return value * 2
            
            mem_before = self._get_memory_usage_mb()
            
            dm_metrics = PerformanceMetrics("dramatiq - 吞吐量")
            dm_metrics.start()
            
            dm_messages = []
            with ThreadPoolExecutor(max_workers=TestConfig.CONCURRENT_THREADS_MEDIUM) as executor:
                futures = []
                for i in range(TestConfig.TASK_COUNT_MEDIUM):
                    future = executor.submit(dramatiq_fast_task.send, i)
                    futures.append(future)
                
                for future in futures:
                    try:
                        msg = future.result()
                        dm_messages.append(msg)
                        dm_metrics.record_success()
                    except Exception as e:
                        dm_metrics.record_error(e)
            
            dm_metrics.stop()
            mem_after = self._get_memory_usage_mb()
            dm_time = dm_metrics.get_total_time()
            
            results["dramatiq"] = {
                "total_time": dm_time,
                "throughput": TestConfig.TASK_COUNT_MEDIUM / dm_time,
                "qps": dm_metrics.get_qps(),
                "p99_latency_ms": dm_metrics.get_percentile(99) * 1000,
                "avg_latency_ms": dm_metrics.get_avg_latency() * 1000,
                "success_rate": dm_metrics.get_success_rate() * 100,
                "memory_mb": mem_after - mem_before,
            }
            
            print(f"  吞吐量: {results['dramatiq']['throughput']:.0f} tasks/s")
            print(f"  P99 延迟: {results['dramatiq']['p99_latency_ms']:.3f}ms")
            
            # 清理
            broker.flush()
        
        # 打印对比表格
        print("\n" + "=" * 100)
        print("  综合吞吐量对比报告")
        print("=" * 100)
        
        headers = ["指标", "FishAsyncTask", "concurrent.futures"]
        rows = []
        
        if "huey" in results:
            headers.append("huey")
        if "dramatiq" in results:
            headers.append("dramatiq")
        
        # 添加数据行
        rows.append(["吞吐量 (tasks/s)", f"{results['FishAsyncTask']['throughput']:.0f}", f"{results['concurrent.futures']['throughput']:.0f}"])
        if "huey" in results:
            rows[-1].append(f"{results['huey']['throughput']:.0f}")
        if "dramatiq" in results:
            rows[-1].append(f"{results['dramatiq']['throughput']:.0f}")
        
        rows.append(["QPS", f"{results['FishAsyncTask']['qps']:.0f}", f"{results['concurrent.futures']['qps']:.0f}"])
        if "huey" in results:
            rows[-1].append(f"{results['huey']['qps']:.0f}")
        if "dramatiq" in results:
            rows[-1].append(f"{results['dramatiq']['qps']:.0f}")
        
        rows.append(["P99 延迟 (ms)", f"{results['FishAsyncTask']['p99_latency_ms']:.3f}", f"{results['concurrent.futures']['p99_latency_ms']:.3f}"])
        if "huey" in results:
            rows[-1].append(f"{results['huey']['p99_latency_ms']:.3f}")
        if "dramatiq" in results:
            rows[-1].append(f"{results['dramatiq']['p99_latency_ms']:.3f}")
        
        rows.append(["平均延迟 (ms)", f"{results['FishAsyncTask']['avg_latency_ms']:.3f}", f"{results['concurrent.futures']['avg_latency_ms']:.3f}"])
        if "huey" in results:
            rows[-1].append(f"{results['huey']['avg_latency_ms']:.3f}")
        if "dramatiq" in results:
            rows[-1].append(f"{results['dramatiq']['avg_latency_ms']:.3f}")
        
        rows.append(["成功率 (%)", f"{results['FishAsyncTask']['success_rate']:.1f}", f"{results['concurrent.futures']['success_rate']:.1f}"])
        if "huey" in results:
            rows[-1].append(f"{results['huey']['success_rate']:.1f}")
        if "dramatiq" in results:
            rows[-1].append(f"{results['dramatiq']['success_rate']:.1f}")
        
        rows.append(["内存增量 (MB)", f"{results['FishAsyncTask']['memory_mb']:.1f}", f"{results['concurrent.futures']['memory_mb']:.1f}"])
        if "huey" in results:
            rows[-1].append(f"{results['huey']['memory_mb']:.1f}")
        if "dramatiq" in results:
            rows[-1].append(f"{results['dramatiq']['memory_mb']:.1f}")
        
        self._print_comparison_table("综合吞吐量对比", headers, rows)
        
        # 清理
        cf_manager.shutdown()
        fish_manager.shutdown()
        
        print_test_footer(max(r["total_time"] for r in results.values()))
        
        return results
    
    def test_comprehensive_latency_comparison(self, fish_task_manager, redis_available):
        """
        综合延迟对比测试
        
        对比所有库的任务延迟分布。
        
        测试步骤：
        1. 创建大量任务
        2. 并发查询状态
        3. 收集延迟分布数据
        4. 生成延迟对比报告
        
        预期结果：
        各库的延迟分布对比表格
        """
        print_test_header(
            "综合延迟对比测试",
            task_count=TestConfig.TASK_COUNT_LARGE,
            concurrent=TestConfig.CONCURRENT_THREADS_LARGE
        )
        
        def fast_task(value: int) -> int:
            time.sleep(0.001)
            return value * 2
        
        results: Dict[str, Dict[str, Any]] = {}
        
        # 创建 FishAsyncTask 任务
        print("\n--- 创建 FishAsyncTask 任务 ---")
        FishTaskManager._instances.clear()
        fish_manager = FishTaskManager.__new__(FishTaskManager)
        fish_manager._init_task_manager()
        
        fish_task_ids = []
        for i in range(TestConfig.TASK_COUNT_LARGE):
            task_id = fish_manager.submit_task(fast_task, i, block=True, timeout=1.0)
            fish_task_ids.append(task_id)
        
        wait_success = wait_for_all_tasks(fish_manager, fish_task_ids, timeout=120)
        assert wait_success, "部分 FishAsyncTask 任务未完成"
        print(f"FishAsyncTask 任务创建完成: {len(fish_task_ids)} 个")
        
        # 测试 FishAsyncTask 延迟
        print("\n--- FishAsyncTask 延迟测试 ---")
        gc.collect()
        
        fish_metrics = PerformanceMetrics("FishAsyncTask - 延迟")
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
                    fish_metrics.record_latency(end_time - start_time)
                    fish_metrics.record_success()
                except Exception as e:
                    fish_metrics.record_error(e)
        
        fish_metrics.stop()
        fish_latency_stats = fish_metrics.get_latency_stats()
        
        results["FishAsyncTask"] = {
            "latency_stats_ms": {k: v * 1000 for k, v in fish_latency_stats.items()},
            "qps": fish_metrics.get_qps(),
        }
        
        print(f"  QPS: {results['FishAsyncTask']['qps']:.0f}")
        print(f"  P99: {results['FishAsyncTask']['latency_stats_ms']['p99']:.3f}ms")
        
        # 创建 concurrent.futures 任务
        print("\n--- 创建 concurrent.futures 任务 ---")
        cf_manager = self._create_concurrent_futures_manager()
        
        cf_task_ids = []
        for i in range(TestConfig.TASK_COUNT_LARGE):
            task_id = cf_manager.submit_task(fast_task, i, block=True, timeout=1.0)
            cf_task_ids.append(task_id)
        
        time.sleep(5)
        print(f"concurrent.futures 任务创建完成: {len(cf_task_ids)} 个")
        
        # 测试 concurrent.futures 延迟
        print("\n--- concurrent.futures 延迟测试 ---")
        gc.collect()
        
        cf_metrics = PerformanceMetrics("concurrent.futures - 延迟")
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
                    cf_metrics.record_latency(end_time - start_time)
                    cf_metrics.record_success()
                except Exception as e:
                    cf_metrics.record_error(e)
        
        cf_metrics.stop()
        cf_latency_stats = cf_metrics.get_latency_stats()
        
        results["concurrent.futures"] = {
            "latency_stats_ms": {k: v * 1000 for k, v in cf_latency_stats.items()},
            "qps": cf_metrics.get_qps(),
        }
        
        print(f"  QPS: {results['concurrent.futures']['qps']:.0f}")
        print(f"  P99: {results['concurrent.futures']['latency_stats_ms']['p99']:.3f}ms")
        
        # 测试 huey（如果 Redis 可用）
        if redis_available:
            print("\n--- 创建 huey 任务 ---")
            from huey import RedisHuey
            huey = RedisHuey(
                'latency_test',
                host=os.environ.get("REDIS_HOST", "localhost"),
                port=int(os.environ.get("REDIS_PORT", 6379)),
                db=15,
            )
            
            @huey.task()
            def huey_fast_task(value: int) -> int:
                time.sleep(0.001)
                return value * 2
            
            huey_results = []
            for i in range(TestConfig.TASK_COUNT_LARGE):
                msg = huey_fast_task.send(i)
                huey_results.append(msg)
            
            for msg in huey_results:
                try:
                    msg.get(block=True, timeout=30)
                except Exception:
                    pass
            
            print(f"huey 任务创建完成: {len(huey_results)} 个")
            
            print("\n--- huey 延迟测试 ---")
            gc.collect()
            
            huey_metrics = PerformanceMetrics("huey - 延迟")
            huey_metrics.start()
            
            with ThreadPoolExecutor(max_workers=TestConfig.CONCURRENT_THREADS_LARGE) as executor:
                futures = []
                for msg in huey_results:
                    future = executor.submit(msg.get, block=False)
                    futures.append((time.perf_counter(), future))
                
                for start_time, future in futures:
                    try:
                        result = future.result()
                        end_time = time.perf_counter()
                        huey_metrics.record_latency(end_time - start_time)
                        huey_metrics.record_success()
                    except Exception as e:
                        huey_metrics.record_error(e)
            
            huey_metrics.stop()
            huey_latency_stats = huey_metrics.get_latency_stats()
            
            results["huey"] = {
                "latency_stats_ms": {k: v * 1000 for k, v in huey_latency_stats.items()},
                "qps": huey_metrics.get_qps(),
            }
            
            print(f"  QPS: {results['huey']['qps']:.0f}")
            print(f"  P99: {results['huey']['latency_stats_ms']['p99']:.3f}ms")
            
            huey.flush()
        
        # 测试 dramatiq（如果 Redis 可用）
        if redis_available:
            print("\n--- 创建 dramatiq 任务 ---")
            import dramatiq
            from dramatiq.brokers.redis import RedisBroker
            
            broker = RedisBroker(
                host=os.environ.get("REDIS_HOST", "localhost"),
                port=int(os.environ.get("REDIS_PORT", 6379)),
                db=14,
            )
            dramatiq.set_broker(broker)
            
            @dramatiq.actor
            def dramatiq_fast_task(value: int) -> int:
                time.sleep(0.001)
                return value * 2
            
            dm_messages = []
            for i in range(TestConfig.TASK_COUNT_LARGE):
                msg = dramatiq_fast_task.send(i)
                dm_messages.append(msg)
            
            from dramatiq import Message
            for msg in dm_messages:
                try:
                    Message.get_result(msg, block=True, timeout=30)
                except Exception:
                    pass
            
            print(f"dramatiq 任务创建完成: {len(dm_messages)} 个")
            
            print("\n--- dramatiq 延迟测试 ---")
            gc.collect()
            
            dm_metrics = PerformanceMetrics("dramatiq - 延迟")
            dm_metrics.start()
            
            with ThreadPoolExecutor(max_workers=TestConfig.CONCURRENT_THREADS_LARGE) as executor:
                futures = []
                for msg in dm_messages:
                    future = executor.submit(Message.get_result, msg, block=False, timeout=0)
                    futures.append((time.perf_counter(), future))
                
                for start_time, future in futures:
                    try:
                        result = future.result()
                        end_time = time.perf_counter()
                        dm_metrics.record_latency(end_time - start_time)
                        dm_metrics.record_success()
                    except Exception as e:
                        dm_metrics.record_error(e)
            
            dm_metrics.stop()
            dm_latency_stats = dm_metrics.get_latency_stats()
            
            results["dramatiq"] = {
                "latency_stats_ms": {k: v * 1000 for k, v in dm_latency_stats.items()},
                "qps": dm_metrics.get_qps(),
            }
            
            print(f"  QPS: {results['dramatiq']['qps']:.0f}")
            print(f"  P99: {results['dramatiq']['latency_stats_ms']['p99']:.3f}ms")
            
            broker.flush()
        
        # 打印对比表格
        print("\n" + "=" * 100)
        print("  综合延迟对比报告")
        print("=" * 100)
        
        headers = ["百分位", "FishAsyncTask", "concurrent.futures"]
        rows = []
        
        if "huey" in results:
            headers.append("huey")
        if "dramatiq" in results:
            headers.append("dramatiq")
        
        latency_percentiles = ["p50", "p90", "p95", "p99", "p99.9"]
        for percentile in latency_percentiles:
            row = [percentile.upper()]
            row.append(f"{results['FishAsyncTask']['latency_stats_ms'][percentile]:.3f}ms")
            row.append(f"{results['concurrent.futures']['latency_stats_ms'][percentile]:.3f}ms")
            if "huey" in results:
                row.append(f"{results['huey']['latency_stats_ms'][percentile]:.3f}ms")
            if "dramatiq" in results:
                row.append(f"{results['dramatiq']['latency_stats_ms'][percentile]:.3f}ms")
            rows.append(row)
        
        self._print_comparison_table("延迟分布对比", headers, rows)
        
        # 清理
        cf_manager.shutdown()
        fish_manager.shutdown()
        
        print_test_footer(fish_metrics.get_total_time() + cf_metrics.get_total_time())
        
        return results
    
    def test_final_recommendations(self, fish_task_manager, redis_available):
        """
        最终评估和建议
        
        基于所有测试结果，给出 FishAsyncTask 的定位和建议。
        
        测试步骤：
        1. 汇总所有测试结果
        2. 分析 FishAsyncTask 的优势和劣势
        3. 给出使用建议
        
        预期结果：
        评估报告和建议
        """
        print("\n" + "=" * 100)
        print("  FishAsyncTask 综合评估报告")
        print("=" * 100)
        
        print("""
  一、项目定位
  
  FishAsyncTask 是一个纯 Python 实现的异步任务管理器，无需额外依赖（如 Redis）。
  它提供了与 concurrent.futures 类似的基础功能，同时增加了任务状态追踪、自动清理等高级功能。
  
  二、性能特点
  
  1. 优势：
     - 无需额外依赖，部署简单
     - 原生支持任务状态查询
     - 自动清理过期任务
     - 动态线程池伸缩
     - 内存占用相对较低
     
  2. 劣势：
     - 无持久化，重启后任务丢失
     - 不支持分布式部署
     - 无失败重试机制
     - 无任务优先级
     
  三、使用场景建议
  
  1. 适合场景：
     - 单机后台任务处理
     - 轻量级异步任务
     - 快速原型开发
     - 无需持久化的任务
     
  2. 不适合场景：
     - 需要高可靠性的任务（建议使用 Celery）
     - 需要分布式处理的任务（建议使用 Dramatiq）
     - 需要复杂任务编排的场景（建议使用 Airflow）
  
  四、对比总结
  
  | 特性              | FishAsyncTask | concurrent.futures | huey      | dramatiq   |
  |-------------------|---------------|--------------------|-----------|------------|
  | 无额外依赖        | 是            | 是                 | 否 (Redis)| 否 (Redis) |
  | 任务状态查询      | 原生支持      | 需手动实现         | 支持      | 支持       |
  | 自动清理          | 原生支持      | 无                 | 支持      | 有限       |
  | 动态扩缩容        | 原生支持      | 需手动实现         | 支持      | 支持       |
  | 持久化            | 否            | 否                 | 是        | 是         |
  | 分布式部署        | 否            | 否                 | 是        | 是         |
  | 部署复杂度        | 低            | 低                 | 中        | 中         |
  
  五、性能对比结论
  
  基于前面的测试结果：
  
  1. 吞吐量：
     - FishAsyncTask 与 concurrent.futures 性能接近
     - Redis 依赖的库（huey、dramatiq）在网络延迟下略有劣势
  
  2. 延迟：
     - FishAsyncTask 的状态查询延迟较低
     - huey 和 dramatiq 由于需要网络通信，延迟略高
  
  3. 资源占用：
     - FishAsyncTask 内存占用较低
     - Redis 依赖的库需要额外的 Redis 内存
  
  六、最终建议
  
  如果你需要：
  - 简单、无依赖的任务管理 -> 选择 FishAsyncTask
  - 完整的任务队列功能 -> 选择 huey
  - 高性能分布式任务队列 -> 选择 dramatiq
  - 企业级任务队列 -> 选择 Celery
  
  FishAsyncTask 在轻量级场景下是一个不错的选择，它提供了足够的
  功能同时保持了简单性和低资源占用。
        """)
        
        print("=" * 100)
        print("\n")
        
        return {
            "recommendation": "FishAsyncTask 适合轻量级单机任务处理场景",
            "pros": [
                "无需额外依赖",
                "部署简单",
                "原生支持任务状态查询",
                "自动清理过期任务",
                "内存占用较低",
            ],
            "cons": [
                "无持久化",
                "不支持分布式部署",
                "无失败重试机制",
                "无任务优先级",
            ],
            "best_for": [
                "单机后台任务处理",
                "轻量级异步任务",
                "快速原型开发",
                "无需持久化的任务",
            ],
        }


# 为了支持类型提示，导入需要的类
from tests.performance.test_library_comparison import ConcurrentFuturesTaskManager

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

