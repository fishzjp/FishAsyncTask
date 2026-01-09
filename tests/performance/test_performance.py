"""
性能基准测试

测试优化前后的性能指标，包括：
- 高并发状态查询性能
- 清理操作性能
- 状态更新吞吐量
"""

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from fish_async_task.task_manager import TaskManager as TaskManagerClass


def simple_task(value: int):
    """简单的测试任务"""
    time.sleep(0.01)  # 10ms执行时间
    return value * 2


def wait_for_all_tasks(task_manager, task_ids, timeout=30):
    """等待所有任务完成"""
    waited = 0
    while waited < timeout:
        all_completed = True
        for task_id in task_ids:
            status = task_manager.get_task_status(task_id)
            if not status or status["status"] not in ("completed", "failed"):
                all_completed = False
                break
        if all_completed:
            return True
        time.sleep(0.1)
        waited += 0.1
    return False


@pytest.fixture(autouse=True)
def cleanup_instances():
    """每个测试前后清理单例实例"""
    TaskManagerClass._instances.clear()
    yield
    TaskManagerClass._instances.clear()


def test_high_concurrent_queries():
    """测试高并发状态查询性能"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    # 创建5000个任务（减少数量，避免队列满）
    task_ids = []
    for i in range(5000):
        # 使用阻塞提交，避免队列满
        try:
            task_id = task_manager.submit_task(simple_task, i, block=True, timeout=1.0)
            task_ids.append(task_id)
        except Exception:
            # 如果队列满，等待一下再继续
            time.sleep(0.1)
            task_id = task_manager.submit_task(simple_task, i, block=True, timeout=1.0)
            task_ids.append(task_id)
    
    # 等待所有任务完成
    assert wait_for_all_tasks(task_manager, task_ids, timeout=120), "任务未在超时时间内完成"
    
    # 并发查询状态（100个并发线程）
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=100) as executor:
        futures = [
            executor.submit(task_manager.get_task_status, task_id)
            for task_id in task_ids
        ]
        results = [f.result() for f in futures]
    end_time = time.time()
    
    # 计算QPS
    elapsed = end_time - start_time
    qps = len(task_ids) / elapsed
    
    # 验证所有查询都成功
    assert len(results) == len(task_ids)
    assert all(r is not None for r in results)
    assert all(r["status"] == "completed" for r in results)
    
    # 输出性能指标
    print(f"\n状态查询性能:")
    print(f"  总任务数: {len(task_ids)}")
    print(f"  并发线程数: 100")
    print(f"  总耗时: {elapsed:.3f}秒")
    print(f"  QPS: {qps:.0f}")
    print(f"  平均延迟: {(elapsed / len(task_ids)) * 1000:.3f}ms")
    
    # 性能断言（目标：QPS >= 8000）
    assert qps >= 8000, f"状态查询 QPS 应该 >= 8000，实际为 {qps:.0f}"
    
    task_manager.shutdown()


def test_cleanup_performance():
    """测试清理操作性能"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    # 创建5000个已完成的任务（使用阻塞提交）
    task_ids = []
    for i in range(5000):
        try:
            task_id = task_manager.submit_task(simple_task, i, block=True, timeout=1.0)
            task_ids.append(task_id)
        except Exception:
            time.sleep(0.1)
            task_id = task_manager.submit_task(simple_task, i, block=True, timeout=1.0)
            task_ids.append(task_id)
    
    # 等待所有任务完成
    assert wait_for_all_tasks(task_manager, task_ids, timeout=60), "任务未在超时时间内完成"
    
    # 设置较短的TTL，使任务过期
    original_ttl = task_manager.task_status_ttl
    task_manager.task_status_ttl = 1  # 1秒TTL
    task_manager.status_manager.task_status_ttl = 1
    task_manager.status_manager.sharded_status.ttl = 1
    
    # 等待任务过期
    time.sleep(2)
    
    # 测试清理性能
    start_time = time.time()
    cleaned = task_manager.status_manager.cleanup_old_task_status()
    end_time = time.time()
    
    cleanup_time = end_time - start_time
    
    # 输出性能指标
    print(f"\n清理操作性能:")
    print(f"  总任务数: {len(task_ids)}")
    print(f"  清理数量: {cleaned}")
    print(f"  清理耗时: {cleanup_time * 1000:.3f}ms")
    
    # 性能断言（目标：清理耗时 <= 10ms）
    assert cleanup_time <= 0.01, f"清理操作耗时应该 <= 10ms，实际为 {cleanup_time * 1000:.3f}ms"
    
    # 恢复原始TTL
    task_manager.task_status_ttl = original_ttl
    task_manager.status_manager.task_status_ttl = original_ttl
    task_manager.status_manager.sharded_status.ttl = original_ttl
    
    task_manager.shutdown()


def test_status_update_throughput():
    """测试状态更新吞吐量"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    # 提交5000个任务并测量吞吐量（使用阻塞提交）
    start_time = time.time()
    task_ids = []
    for i in range(5000):
        try:
            task_id = task_manager.submit_task(simple_task, i, block=True, timeout=1.0)
            task_ids.append(task_id)
        except Exception:
            time.sleep(0.1)
            task_id = task_manager.submit_task(simple_task, i, block=True, timeout=1.0)
            task_ids.append(task_id)
    end_time = time.time()
    
    submission_time = end_time - start_time
    throughput = len(task_ids) / submission_time if submission_time > 0 else 0
    
    # 输出性能指标
    print(f"\n状态更新吞吐量:")
    print(f"  总任务数: {len(task_ids)}")
    print(f"  提交耗时: {submission_time:.3f}秒")
    print(f"  吞吐量: {throughput:.0f} tasks/s")
    
    # 验证所有任务都已提交
    assert len(task_ids) == 5000
    
    # 等待所有任务完成
    assert wait_for_all_tasks(task_manager, task_ids, timeout=60), "任务未在超时时间内完成"
    
    task_manager.shutdown()


def test_concurrent_query_latency():
    """测试并发查询延迟（P50, P99）"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    # 创建1000个任务
    task_ids = []
    for i in range(1000):
        task_id = task_manager.submit_task(simple_task, i)
        task_ids.append(task_id)
    
    # 等待所有任务完成
    assert wait_for_all_tasks(task_manager, task_ids, timeout=30), "任务未在超时时间内完成"
    
    # 并发查询并测量延迟
    latencies = []
    with ThreadPoolExecutor(max_workers=100) as executor:
        def query_with_timing(task_id: str):
            start = time.time()
            result = task_manager.get_task_status(task_id)
            end = time.time()
            return (end - start) * 1000  # 转换为毫秒
        
        futures = [executor.submit(query_with_timing, task_id) for task_id in task_ids]
        latencies = [f.result() for f in futures]
    
    # 计算统计指标
    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p99 = latencies[int(len(latencies) * 0.99)]
    avg = sum(latencies) / len(latencies)
    
    # 输出性能指标
    print(f"\n并发查询延迟:")
    print(f"  总查询数: {len(latencies)}")
    print(f"  平均延迟: {avg:.3f}ms")
    print(f"  P50延迟: {p50:.3f}ms")
    print(f"  P99延迟: {p99:.3f}ms")
    
    # 性能断言（目标：P99延迟 <= 5ms）
    assert p99 <= 5.0, f"P99延迟应该 <= 5ms，实际为 {p99:.3f}ms"
    
    task_manager.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

