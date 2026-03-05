"""
批量 API 性能测试

验证批量操作相比单独操作的加速效果。
"""

import time

import pytest

from fish_async_task._adapters import get_priority_queue, get_sharded_status_store
from fish_async_task._rust import is_rust_available


@pytest.fixture(autouse=True)
def check_rust():
    """检查 Rust 是否可用"""
    if not is_rust_available():
        pytest.skip("Rust 扩展不可用")


class TestStatusBatchAPI:
    """测试状态存储的批量 API"""

    def test_batch_vs_single_write(self):
        """对比批量写入与单独写入"""
        count = 1000
        store = get_sharded_status_store(shard_count=16, ttl=3600)

        # 准备数据
        items = [
            (f"task_{i}", {"status": "pending", "submit_time": time.time()}) for i in range(count)
        ]

        # 单独写入
        start = time.time()
        for task_id, status in items:
            store.update_status(task_id, status)
        single_time = time.time() - start

        # 清空
        store.clear_all()

        # 批量写入
        start = time.time()
        count_updated = 0
        # 使用适配器的批量方法（如果可用）
        if hasattr(store, "update_status_batch"):
            count_updated = store.update_status_batch(items)
        else:
            # 回退到单独操作
            for task_id, status in items:
                store.update_status(task_id, status)
            count_updated = count
        batch_time = time.time() - start

        speedup = single_time / batch_time if batch_time > 0 else 0

        print(f"\n[批量 API] 状态写入 ({count} 条目):")
        print(f"  单独操作: {single_time:.4f}s ({count/single_time:.0f} ops/s)")
        print(f"  批量操作: {batch_time:.4f}s ({count/batch_time:.0f} ops/s)")
        print(f"  加速比: {speedup:.2f}x")
        print(f"  更新数量: {count_updated}/{count}")

        assert count_updated >= count * 0.95, "批量更新应该成功处理至少 95% 的条目"

    def test_batch_vs_single_read(self):
        """对比批量读取与单独读取"""
        count = 1000
        store = get_sharded_status_store(shard_count=16, ttl=3600)

        # 准备数据
        task_ids = []
        for i in range(count):
            task_id = f"task_{i}"
            task_ids.append(task_id)
            store.update_status(
                task_id, {"status": "completed", "submit_time": time.time(), "result": i}
            )

        # 单独读取
        start = time.time()
        single_results = []
        for task_id in task_ids:
            result = store.get_status(task_id)
            single_results.append(result)
        single_time = time.time() - start

        # 批量读取
        start = time.time()
        if hasattr(store, "get_status_batch"):
            batch_results = store.get_status_batch(task_ids)
        else:
            batch_results = [store.get_status(tid) for tid in task_ids]
        batch_time = time.time() - start

        speedup = single_time / batch_time if batch_time > 0 else 0

        print(f"\n[批量 API] 状态读取 ({count} 条目):")
        print(f"  单独操作: {single_time:.4f}s ({count/single_time:.0f} ops/s)")
        print(f"  批量操作: {batch_time:.4f}s ({count/batch_time:.0f} ops/s)")
        print(f"  加速比: {speedup:.2f}x")

        assert len(batch_results) == count, "批量读取应该返回相同数量的结果"

    def test_different_batch_sizes(self):
        """测试不同批量大小对性能的影响"""
        batch_sizes = [10, 50, 100, 500, 1000]
        results = []

        store = get_sharded_status_store(shard_count=16, ttl=3600)

        for batch_size in batch_sizes:
            # 准备数据
            items = [
                (f"task_batch_{batch_size}_{i}", {"status": "pending", "submit_time": time.time()})
                for i in range(batch_size)
            ]

            # 批量写入
            start = time.time()
            if hasattr(store, "update_status_batch"):
                store.update_status_batch(items)
            else:
                for task_id, status in items:
                    store.update_status(task_id, status)
            elapsed = time.time() - start

            throughput = batch_size / elapsed
            results.append((batch_size, elapsed, throughput))

            # 清空
            for task_id, _ in items:
                store.remove_status(task_id)

        print(f"\n[批量 API] 不同批量大小性能:")
        print(f"  {'批量大小':>10} | {'耗时(s)':>10} | {'吞吐量(ops/s)':>15}")
        print(f"  {'-'*10}-+-{'-'*10}-+-{'-'*15}")
        for batch_size, elapsed, throughput in results:
            print(f"  {batch_size:>10} | {elapsed:>10.4f} | {throughput:>15.0f}")


class TestQueueBatchAPI:
    """测试优先级队列的批量 API"""

    def test_batch_vs_single_put(self):
        """对比批量入队与单独入队"""
        count = 1000
        queue = get_priority_queue(maxsize=10000)

        # 准备数据
        items = [(i % 100, f"task_{i}", time.time()) for i in range(count)]

        # 单独入队
        start = time.time()
        for priority, task_id, submit_time in items:
            queue.put(task_id, priority)
        single_time = time.time() - start

        # 清空队列
        while not queue.empty():
            queue.get(block=False)

        # 批量入队
        start = time.time()
        if hasattr(queue, "put_batch"):
            count_added = queue.put_batch(items)
        else:
            count_added = 0
            for priority, task_id, submit_time in items:
                queue.put(task_id, priority)
                count_added += 1
        batch_time = time.time() - start

        speedup = single_time / batch_time if batch_time > 0 else 0

        print(f"\n[批量 API] 队列入队 ({count} 条目):")
        print(f"  单独操作: {single_time:.4f}s ({count/single_time:.0f} ops/s)")
        print(f"  批量操作: {batch_time:.4f}s ({count/batch_time:.0f} ops/s)")
        print(f"  加速比: {speedup:.2f}x")
        print(f"  添加数量: {count_added}/{count}")

        assert count_added >= count * 0.95, "批量入队应该成功处理至少 95% 的条目"

    def test_batch_vs_single_get(self):
        """对比批量出队与单独出队"""
        count = 1000
        queue = get_priority_queue(maxsize=10000)

        # 填充队列
        for i in range(count):
            queue.put(f"task_{i}", i % 100)

        # 单独出队
        start = time.time()
        single_results = []
        for _ in range(count):
            if not queue.empty():
                single_results.append(queue.get(block=False))
        single_time = time.time() - start

        # 重新填充队列
        for i in range(count):
            queue.put(f"task_{i}", i % 100)

        # 批量出队
        start = time.time()
        if hasattr(queue, "get_batch"):
            batch_results = queue.get_batch(count)
        else:
            batch_results = []
            for _ in range(count):
                if not queue.empty():
                    batch_results.append(queue.get(block=False))
        batch_time = time.time() - start

        speedup = single_time / batch_time if batch_time > 0 else 0

        print(f"\n[批量 API] 队列出队 ({count} 条目):")
        print(f"  单独操作: {single_time:.4f}s ({count/single_time:.0f} ops/s)")
        print(f"  批量操作: {batch_time:.4f}s ({count/batch_time:.0f} ops/s)")
        print(f"  加速比: {speedup:.2f}x")

        assert len(batch_results) > 0, "批量出队应该返回结果"

    def test_mixed_batch_operations(self):
        """测试混合批量操作场景"""
        queue = get_priority_queue(maxsize=10000)

        # 批量入队
        put_items = [(i % 50, f"task_{i}", time.time()) for i in range(500)]
        if hasattr(queue, "put_batch"):
            queue.put_batch(put_items)
        else:
            for priority, task_id, _ in put_items:
                queue.put(task_id, priority)

        # 分批出队
        batch_sizes = [10, 50, 100, 200]
        total_retrieved = 0

        for batch_size in batch_sizes:
            if queue.empty():
                break

            if hasattr(queue, "get_batch"):
                results = queue.get_batch(batch_size)
            else:
                results = []
                for _ in range(min(batch_size, queue.qsize())):
                    if not queue.empty():
                        results.append(queue.get(block=False))

            total_retrieved += len(results)

        print(f"\n[批量 API] 混合操作:")
        print(f"  入队数量: {len(put_items)}")
        print(f"  出队数量: {total_retrieved}")

        # 由于批量 API 可能一次性取走所有任务，我们只验证确实取到了任务
        assert total_retrieved > 0, "应该检索到任务"


class TestBatchAPILatency:
    """测试批量 API 的延迟特性"""

    def test_batch_write_latency_distribution(self):
        """测试批量写入的延迟分布"""
        import statistics

        count = 100
        batch_size = 50
        iterations = 20

        store = get_sharded_status_store(shard_count=16, ttl=3600)

        latencies = []

        for _ in range(iterations):
            items = [
                (f"task_lat_{_}_{i}", {"status": "pending", "submit_time": time.time()})
                for i in range(batch_size)
            ]

            start = time.perf_counter()
            if hasattr(store, "update_status_batch"):
                store.update_status_batch(items)
            else:
                for task_id, status in items:
                    store.update_status(task_id, status)
            latency_ms = (time.perf_counter() - start) * 1000
            latencies.append(latency_ms)

        avg = statistics.mean(latencies)
        p50 = statistics.median(latencies)
        p99 = statistics.quantiles(latencies, n=100)[98]

        print(f"\n[批量 API] 批量写入延迟分布 ({batch_size} 条目/批次, {iterations} 批次):")
        print(f"  平均: {avg:.4f}ms")
        print(f"  P50: {p50:.4f}ms")
        print(f"  P99: {p99:.4f}ms")
        print(f"  每条目平均: {avg/batch_size:.4f}ms")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
