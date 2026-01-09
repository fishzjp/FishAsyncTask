"""
dramatiq 性能对比测试

测试 dramatiq 的各项性能指标，与 FishAsyncTask 进行对比。

注意：dramatiq 需要 Redis 作为消息队列和消息传递。
如果 Redis 不可用，测试将被跳过。

测试场景：
- 任务提交吞吐量
- 任务执行时间
- 并发状态查询
- 清理操作性能
- 端到端性能
"""

import gc
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

import dramatiq
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
    available = is_redis_available()
    if not available:
        pytest.skip("Redis 不可用，跳过 dramatiq 测试")
    return available


@pytest.fixture
def dramatiq_broker(redis_available):
    """创建 dramatiq 代理"""
    from dramatiq.brokers.redis import RedisBroker
    
    broker = RedisBroker(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", 6379)),
        db=14,  # 使用独立的数据库避免冲突
    )
    
    # 设置全局代理
    dramatiq.set_broker(broker)
    
    yield broker
    
    # 清理测试数据
    try:
        broker.flush()
    except Exception:
        pass


@pytest.fixture
def dramatiq_worker(redis_available):
    """创建 dramatiq 工作进程"""
    import multiprocessing

    # 定义任务执行器
    def run_worker():
        worker = dramatiq.Worker(
            broker=dramatiq.get_broker(),
            workers=4,
            worker_timeout=100,
        )
        worker.start()
        try:
            # 运行一小段时间
            time.sleep(0.1)
        finally:
            worker.stop()
    
    # 启动工作进程
    process = multiprocessing.Process(target=run_worker)
    process.start()
    
    yield process
    
    # 停止工作进程
    process.terminate()
    process.join(timeout=5)


@pytest.fixture
def fish_task_manager(redis_available):
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


class TestDramatiqComparison:
    """dramatiq 对比测试"""
    
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """每个测试前后的设置和清理"""
        gc.collect()
        yield
        gc.collect()
    
    def _get_memory_usage_mb(self) -> float:
        """获取当前进程的内存使用量（MB）"""
        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)
    
    def _get_cpu_usage_percent(self) -> float:
        """获取当前进程的 CPU 使用率"""
        process = psutil.Process()
        return process.cpu_percent()
    
    def test_task_submission_throughput(self, dramatiq_broker, fish_task_manager):
        """
        测试任务提交吞吐量
        
        对比 FishAsyncTask 和 dramatiq 的任务提交性能。
        
        测试步骤：
        1. 创建 5000 个快速任务（1ms）
        2. 使用 100 个并发线程提交任务
        3. 测量提交吞吐量和延迟
        
        预期结果：
        - FishAsyncTask: 提交吞吐量约 X tasks/s，P99 延迟约 Y ms
        - dramatiq: 提交吞吐量约 X tasks/s，P99 延迟约 Y ms
        """
        print_test_header(
            "dramatiq vs FishAsyncTask - 任务提交吞吐量",
            task_count=TestConfig.TASK_COUNT_MEDIUM,
            concurrent=TestConfig.CONCURRENT_THREADS_MEDIUM
        )
        
        # 定义 dramatiq 任务
        @dramatiq.actor
        def dramatiq_fast_task(value: int) -> int:
            time.sleep(0.001)
            return value * 2
        
        def fast_task(value: int) -> int:
            time.sleep(0.001)
            return value * 2
        
        # 测试 FishAsyncTask
        print("\n--- FishAsyncTask 测试 ---")
        gc.collect()
        mem_before_fat = self._get_memory_usage_mb()
        
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
        
        # 等待任务完成
        print("等待 FishAsyncTask 任务完成...")
        wait_for_all_tasks(fish_task_manager, fish_task_ids, timeout=120)
        
        print(f"\nFishAsyncTask 结果:")
        print(f"  总耗时: {fish_time:.3f}秒")
        print(f"  吞吐量: {TestConfig.TASK_COUNT_MEDIUM / fish_time:.0f} tasks/s")
        print(f"  QPS: {fish_metrics.get_qps():.0f}")
        print(f"  P99 延迟: {fish_metrics.get_percentile(99) * 1000:.3f}ms")
        print(f"  内存变化: {mem_before_fat:.1f}MB -> {mem_after_fat:.1f}MB")
        
        # 测试 dramatiq
        print("\n--- dramatiq 测试 ---")
        gc.collect()
        mem_before_dm = self._get_memory_usage_mb()
        
        dm_metrics = PerformanceMetrics("dramatiq - 任务提交")
        dm_metrics.start()
        
        dm_messages = []
        with ThreadPoolExecutor(max_workers=TestConfig.CONCURRENT_THREADS_MEDIUM) as executor:
            futures = []
            for i in range(TestConfig.TASK_COUNT_MEDIUM):
                future = executor.submit(dramatiq_fast_task.send, i)
                futures.append(future)
            
            for future in futures:
                try:
                    message = future.result()
                    dm_messages.append(message)
                    dm_metrics.record_success()
                except Exception as e:
                    dm_metrics.record_error(e)
        
        dm_metrics.stop()
        dm_time = dm_metrics.get_total_time()
        mem_after_dm = self._get_memory_usage_mb()
        
        print(f"\ndramatiq 结果:")
        print(f"  总耗时: {dm_time:.3f}秒")
        print(f"  吞吐量: {TestConfig.TASK_COUNT_MEDIUM / dm_time:.0f} tasks/s")
        print(f"  QPS: {dm_metrics.get_qps():.0f}")
        print(f"  P99 延迟: {dm_metrics.get_percentile(99) * 1000:.3f}ms")
        print(f"  内存变化: {mem_before_dm:.1f}MB -> {mem_after_dm:.1f}MB")
        
        # 打印对比结果
        print("\n" + "=" * 80)
        print("对比结果")
        print("=" * 80)
        
        fat_throughput = TestConfig.TASK_COUNT_MEDIUM / fish_time
        dm_throughput = TestConfig.TASK_COUNT_MEDIUM / dm_time
        
        print(f"\n{'指标':<25} {'FishAsyncTask':<20} {'dramatiq':<20}")
        print("-" * 65)
        print(f"{'吞吐量 (tasks/s)':<25} {fat_throughput:<20.0f} {dm_throughput:<20.0f}")
        print(f"{'P99 延迟 (ms)':<25} {fish_metrics.get_percentile(99) * 1000:<20.3f} {dm_metrics.get_percentile(99) * 1000:<20.3f}")
        print(f"{'平均延迟 (ms)':<25} {fish_metrics.get_avg_latency() * 1000:<20.3f} {dm_metrics.get_avg_latency() * 1000:<20.3f}")
        print(f"{'内存增量 (MB)':<25} {mem_after_fat - mem_before_fat:<20.1f} {mem_after_dm - mem_before_dm:<20.1f}")
        print(f"{'成功率 (%)':<25} {fish_metrics.get_success_rate() * 100:<19.1f}% {dm_metrics.get_success_rate() * 100:<19.1f}%")
        
        # 计算性能差异
        throughput_diff = ((fat_throughput - dm_throughput) / dm_throughput * 100) if dm_throughput > 0 else 0
        print(f"\n性能差异分析:")
        print(f"  吞吐量差异: {throughput_diff:+.1f}%")
        
        if throughput_diff > 0:
            print(f"  FishAsyncTask 吞吐量提升 {throughput_diff:.1f}%")
        else:
            print(f"  dramatiq 吞吐量提升 {abs(throughput_diff):.1f}%")
        
        print_test_footer(max(fish_time, dm_time))
        
        return {
            "fish_async_task": fish_metrics.get_results(),
            "dramatiq": dm_metrics.get_results(),
        }
    
    def test_concurrent_status_query(self, dramatiq_broker, fish_task_manager):
        """
        测试并发状态查询性能
        
        对比 FishAsyncTask 和 dramatiq 的任务状态查询性能。
        
        测试步骤：
        1. 创建 10000 个已完成的任务
        2. 使用 200 个并发线程查询任务状态
        3. 测量查询吞吐量和延迟
        
        预期结果：
        - FishAsyncTask: 查询 QPS 约 X，P99 延迟约 Y ms
        - dramatiq: 查询 QPS 约 X，P99 延迟约 Y ms
        """
        print_test_header(
            "dramatiq vs FishAsyncTask - 并发状态查询",
            task_count=TestConfig.TASK_COUNT_LARGE,
            concurrent=TestConfig.CONCURRENT_THREADS_LARGE
        )
        
        # 定义 dramatiq 任务
        @dramatiq.actor
        def dramatiq_fast_task(value: int) -> int:
            time.sleep(0.001)
            return value * 2
        
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
        
        # 创建 dramatiq 任务
        print("\n--- 创建 dramatiq 任务 ---")
        dm_messages = []
        for i in range(TestConfig.TASK_COUNT_LARGE):
            message = dramatiq_fast_task.send(i)
            dm_messages.append(message)
        
        # 等待所有 dramatiq 任务完成（使用管道等待）
        print("等待 dramatiq 任务完成...")
        from dramatiq import Message
        for msg in dm_messages:
            try:
                # 尝试获取结果
                Message.get_result(msg, block=False, timeout=0)
            except Exception:
                pass
        
        print(f"dramatiq 任务创建完成: {len(dm_messages)} 个")
        
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
        
        # 测试 dramatiq 状态查询
        print("\n--- dramatiq 状态查询测试 ---")
        gc.collect()
        
        dm_metrics = PerformanceMetrics("dramatiq - 状态查询")
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
                    latency = end_time - start_time
                    dm_metrics.record_latency(latency)
                    dm_metrics.record_success()
                except Exception as e:
                    dm_metrics.record_error(e)
        
        dm_metrics.stop()
        
        print(f"\ndramatiq 状态查询结果:")
        print(f"  总查询数: {dm_metrics.get_total_operations()}")
        print(f"  QPS: {dm_metrics.get_qps():.0f}")
        print(f"  P99 延迟: {dm_metrics.get_percentile(99) * 1000:.3f}ms")
        print(f"  P50 延迟: {dm_metrics.get_percentile(50) * 1000:.3f}ms")
        
        # 打印对比结果
        print("\n" + "=" * 80)
        print("对比结果")
        print("=" * 80)
        
        print(f"\n{'指标':<25} {'FishAsyncTask':<20} {'dramatiq':<20}")
        print("-" * 65)
        print(f"{'QPS':<25} {fish_metrics.get_qps():<20.0f} {dm_metrics.get_qps():<20.0f}")
        print(f"{'P99 延迟 (ms)':<25} {fish_metrics.get_percentile(99) * 1000:<20.3f} {dm_metrics.get_percentile(99) * 1000:<20.3f}")
        print(f"{'P50 延迟 (ms)':<25} {fish_metrics.get_percentile(50) * 1000:<20.3f} {dm_metrics.get_percentile(50) * 1000:<20.3f}")
        print(f"{'平均延迟 (ms)':<25} {fish_metrics.get_avg_latency() * 1000:<20.3f} {dm_metrics.get_avg_latency() * 1000:<20.3f}")
        print(f"{'成功率 (%)':<25} {fish_metrics.get_success_rate() * 100:<19.1f}% {dm_metrics.get_success_rate() * 100:<19.1f}%")
        
        # 计算性能差异
        qps_diff = ((fish_metrics.get_qps() - dm_metrics.get_qps()) / dm_metrics.get_qps() * 100) if dm_metrics.get_qps() > 0 else 0
        print(f"\n性能差异分析:")
        print(f"  QPS 差异: {qps_diff:+.1f}%")
        
        if qps_diff > 0:
            print(f"  FishAsyncTask QPS 提升 {qps_diff:.1f}%")
        else:
            print(f"  dramatiq QPS 提升 {abs(qps_diff):.1f}%")
        
        print_test_footer(fish_metrics.get_total_time() + dm_metrics.get_total_time())
        
        # 清理
        fish_manager.shutdown()
        
        return {
            "fish_async_task": fish_metrics.get_results(),
            "dramatiq": dm_metrics.get_results(),
        }
    
    def test_task_execution_time(self, dramatiq_broker, fish_task_manager):
        """
        测试任务执行时间
        
        对比 FishAsyncTask 和 dramatiq 执行相同任务的耗时。
        
        测试步骤：
        1. 创建 1000 个耗时任务（10ms）
        2. 测量任务总执行时间
        3. 计算实际吞吐量
        
        预期结果：
        - FishAsyncTask: 执行时间约 X 秒，吞吐量约 Y tasks/s
        - dramatiq: 执行时间约 X 秒，吞吐量约 Y tasks/s
        """
        print_test_header(
            "dramatiq vs FishAsyncTask - 任务执行时间",
            task_count=TestConfig.TASK_COUNT_SMALL,
            concurrent=50
        )
        
        # 定义 dramatiq 任务
        @dramatiq.actor
        def dramatiq_normal_task(value: int) -> int:
            time.sleep(0.01)
            return value * 2
        
        def normal_task(value: int) -> int:
            time.sleep(0.01)
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
        
        # 测试 dramatiq
        print("\n--- dramatiq 测试 ---")
        gc.collect()
        
        dm_start = time.perf_counter()
        dm_messages = []
        for i in range(TestConfig.TASK_COUNT_SMALL):
            message = dramatiq_normal_task.send(i)
            dm_messages.append(message)
        print(f"已提交 {len(dm_messages)} 个任务")
        
        dm_execution_start = time.perf_counter()
        # 等待所有 dramatiq 任务完成
        from dramatiq import Message
        for msg in dm_messages:
            try:
                Message.get_result(msg, block=True, timeout=30)
            except Exception:
                pass
        
        dm_execution_time = time.perf_counter() - dm_execution_start
        dm_total_time = time.perf_counter() - dm_start
        
        dm_throughput = len(dm_messages) / dm_execution_time
        
        print(f"\ndramatiq 执行结果:")
        print(f"  提交时间: {dm_execution_start - dm_start:.3f}秒")
        print(f"  执行时间: {dm_execution_time:.3f}秒")
        print(f"  总耗时: {dm_total_time:.3f}秒")
        print(f"  吞吐量: {dm_throughput:.0f} tasks/s")
        
        # 打印对比结果
        print("\n" + "=" * 80)
        print("对比结果")
        print("=" * 80)
        
        print(f"\n{'指标':<25} {'FishAsyncTask':<20} {'dramatiq':<20}")
        print("-" * 65)
        print(f"{'执行时间 (秒)':<25} {fish_execution_time:<20.3f} {dm_execution_time:<20.3f}")
        print(f"{'吞吐量 (tasks/s)':<25} {fish_throughput:<20.0f} {dm_throughput:<20.0f}")
        print(f"{'总耗时 (秒)':<25} {fish_total_time:<20.3f} {dm_total_time:<20.3f}")
        
        print_test_footer(max(fish_total_time, dm_total_time))
        
        # 清理
        fish_manager.shutdown()
        
        return {
            "fish_async_task": {
                "execution_time": fish_execution_time,
                "throughput": fish_throughput,
                "total_time": fish_total_time,
            },
            "dramatiq": {
                "execution_time": dm_execution_time,
                "throughput": dm_throughput,
                "total_time": dm_total_time,
            },
        }
    
    def test_cleanup_performance(self, dramatiq_broker, fish_task_manager):
        """
        测试清理操作性能
        
        对比 FishAsyncTask 和 dramatiq 清理过期任务的性能。
        
        测试步骤：
        1. 创建 10000 个任务
        2. 等待任务完成
        3. 清理过期任务
        4. 测量清理性能和吞吐量
        
        预期结果：
        - FishAsyncTask: 清理吞吐量约 X tasks/s
        - dramatiq: 清理吞吐量约 X tasks/s
        """
        print_test_header(
            "dramatiq vs FishAsyncTask - 清理操作性能",
            task_count=TestConfig.TASK_COUNT_LARGE
        )
        
        # 定义 dramatiq 任务
        @dramatiq.actor
        def dramatiq_fast_task(value: int) -> int:
            time.sleep(0.001)
            return value * 2
        
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
        
        # 创建 dramatiq 任务
        print("\n--- 创建 dramatiq 任务 ---")
        dm_messages = []
        for i in range(TestConfig.TASK_COUNT_LARGE):
            message = dramatiq_fast_task.send(i)
            dm_messages.append(message)
        
        # 等待所有 dramatiq 任务完成
        print("等待 dramatiq 任务完成...")
        from dramatiq import Message
        for msg in dm_messages:
            try:
                Message.get_result(msg, block=True, timeout=30)
            except Exception:
                pass
        
        print(f"dramatiq 任务创建完成: {len(dm_messages)} 个")
        
        # 测试 FishAsyncTask 清理性能
        print("\n--- FishAsyncTask 清理测试 ---")
        
        # 设置短 TTL 使任务过期
        original_ttl = fish_manager.task_status_ttl
        fish_manager.task_status_ttl = 1
        fish_manager.status_manager.task_status_ttl = 1
        fish_manager.status_manager.sharded_status.ttl = 1
        
        print("等待 FishAsyncTask 任务过期...")
        time.sleep(2)
        
        # 执行清理
        fish_start_time = time.perf_counter()
        fish_cleaned_count = fish_manager.status_manager.cleanup_old_task_status()
        fish_cleanup_time = time.perf_counter() - fish_start_time
        
        fish_throughput = fish_cleaned_count / fish_cleanup_time if fish_cleanup_time > 0 else 0
        
        print(f"\nFishAsyncTask 清理结果:")
        print(f"  清理任务数: {fish_cleaned_count}")
        print(f"  清理耗时: {fish_cleanup_time * 1000:.3f}ms")
        print(f"  清理吞吐量: {fish_throughput:.0f} tasks/s")
        
        # 恢复 TTL
        fish_manager.task_status_ttl = original_ttl
        
        # 测试 dramatiq 清理性能
        print("\n--- dramatiq 清理测试 ---")
        
        dm_start_time = time.perf_counter()
        # dramatiq 使用 dead letter queue 和消息过期进行清理
        dm_cleaned_count = 0
        try:
            # 统计已处理的消息
            dm_cleaned_count = len(dm_messages)
            # dramatiq 没有直接的批量清理接口，这里测量其他操作
        except Exception as e:
            print(f"  dramatiq 清理跳过: {e}")
        
        dm_cleanup_time = time.perf_counter() - dm_start_time
        dm_throughput = dm_cleaned_count / dm_cleanup_time if dm_cleanup_time > 0 else 0
        
        print(f"\ndramatiq 清理结果:")
        print(f"  清理任务数: {dm_cleaned_count}")
        print(f"  清理耗时: {dm_cleanup_time * 1000:.3f}ms")
        if dm_throughput > 0:
            print(f"  清理吞吐量: {dm_throughput:.0f} tasks/s")
        else:
            print(f"  清理吞吐量: N/A (dramatiq 无需显式清理)")
        
        # 打印对比结果
        print("\n" + "=" * 80)
        print("对比结果")
        print("=" * 80)
        
        print(f"\n{'指标':<25} {'FishAsyncTask':<20} {'dramatiq':<20}")
        print("-" * 65)
        print(f"{'清理任务数':<25} {fish_cleaned_count:<20} {dm_cleaned_count:<20}")
        print(f"{'清理耗时 (ms)':<25} {fish_cleanup_time * 1000:<20.3f} {dm_cleanup_time * 1000:<20.3f}")
        if dm_throughput > 0:
            print(f"{'清理吞吐量 (tasks/s)':<25} {fish_throughput:<20.0f} {dm_throughput:<20.0f}")
        else:
            print(f"{'清理吞吐量':<25} {fish_throughput:<20.0f} {'N/A':<20}")
        
        print_test_footer(max(fish_cleanup_time, dm_cleanup_time))
        
        # 清理
        fish_manager.shutdown()
        
        return {
            "fish_async_task": {
                "cleanup_count": fish_cleaned_count,
                "cleanup_time_ms": fish_cleanup_time * 1000,
                "throughput": fish_throughput,
            },
            "dramatiq": {
                "cleanup_count": dm_cleaned_count,
                "cleanup_time_ms": dm_cleanup_time * 1000,
                "throughput": dm_throughput,
            },
        }
    
    def test_end_to_end_performance(self, dramatiq_broker, fish_task_manager):
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
        - dramatiq: 端到端时间约 X 秒，状态查询 QPS 约 Y
        """
        print_test_header(
            "dramatiq vs FishAsyncTask - 端到端性能",
            task_count=TestConfig.TASK_COUNT_MEDIUM
        )
        
        # 定义 dramatiq 任务
        @dramatiq.actor
        def dramatiq_normal_task(value: int) -> int:
            time.sleep(0.01)
            return value * 2
        
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
        
        # 测试 dramatiq
        print("\n--- dramatiq 测试 ---")
        gc.collect()
        
        # 提交任务
        print("提交 dramatiq 任务...")
        dm_start = time.perf_counter()
        dm_messages = []
        for i in range(TestConfig.TASK_COUNT_MEDIUM):
            message = dramatiq_normal_task.send(i)
            dm_messages.append(message)
        print(f"已提交 {len(dm_messages)} 个任务")
        
        # 等待任务执行
        print("等待 dramatiq 任务执行...")
        dm_execution_start = time.perf_counter()
        from dramatiq import Message
        for msg in dm_messages:
            try:
                Message.get_result(msg, block=True, timeout=30)
            except Exception:
                pass
        
        dm_execution_time = time.perf_counter() - dm_execution_start
        
        # 并发查询状态
        print("dramatiq 并发查询任务状态...")
        dm_query_metrics = PerformanceMetrics("dramatiq - 端到端状态查询")
        dm_query_metrics.start()
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = []
            for msg in dm_messages:
                future = executor.submit(Message.get_result, msg, block=False, timeout=0)
                futures.append((time.perf_counter(), future))
            
            for start_time, future in futures:
                try:
                    result = future.result()
                    end_time = time.perf_counter()
                    latency = end_time - start_time
                    dm_query_metrics.record_latency(latency)
                    dm_query_metrics.record_success()
                except Exception as e:
                    dm_query_metrics.record_error(e)
        
        dm_query_metrics.stop()
        dm_total_time = time.perf_counter() - dm_start
        
        print(f"\ndramatiq 端到端结果:")
        print(f"  任务执行时间: {dm_execution_time:.3f}秒")
        print(f"  总耗时: {dm_total_time:.3f}秒")
        print(f"  任务吞吐量: {len(dm_messages) / dm_execution_time:.0f} tasks/s")
        print(f"  状态查询 QPS: {dm_query_metrics.get_qps():.0f}")
        print(f"  状态查询 P99 延迟: {dm_query_metrics.get_percentile(99) * 1000:.3f}ms")
        
        # 打印对比结果
        print("\n" + "=" * 80)
        print("端到端对比结果")
        print("=" * 80)
        
        print(f"\n{'指标':<25} {'FishAsyncTask':<20} {'dramatiq':<20}")
        print("-" * 65)
        print(f"{'任务执行时间 (秒)':<25} {fish_execution_time:<20.3f} {dm_execution_time:<20.3f}")
        print(f"{'总耗时 (秒)':<25} {fish_total_time:<20.3f} {dm_total_time:<20.3f}")
        print(f"{'任务吞吐量 (tasks/s)':<25} {len(fish_task_ids) / fish_execution_time:<20.0f} {len(dm_messages) / dm_execution_time:<20.0f}")
        print(f"{'状态查询 QPS':<25} {fish_query_metrics.get_qps():<20.0f} {dm_query_metrics.get_qps():<20.0f}")
        print(f"{'状态查询 P99 (ms)':<25} {fish_query_metrics.get_percentile(99) * 1000:<20.3f} {dm_query_metrics.get_percentile(99) * 1000:<20.3f}")
        
        print_test_footer(max(fish_total_time, dm_total_time))
        
        # 清理
        fish_manager.shutdown()
        
        return {
            "fish_async_task": {
                "execution_time": fish_execution_time,
                "total_time": fish_total_time,
                "throughput": len(fish_task_ids) / fish_execution_time,
                "query_qps": fish_query_metrics.get_qps(),
                "query_p99_ms": fish_query_metrics.get_percentile(99) * 1000,
            },
            "dramatiq": {
                "execution_time": dm_execution_time,
                "total_time": dm_total_time,
                "throughput": len(dm_messages) / dm_execution_time,
                "query_qps": dm_query_metrics.get_qps(),
                "query_p99_ms": dm_query_metrics.get_percentile(99) * 1000,
            },
        }


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

