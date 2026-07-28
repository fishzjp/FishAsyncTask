"""
Rust vs Python 性能对比测试

比较 Rust 实现与 Python 实现的性能差异。
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from fish_async_task._adapters import get_priority_queue, get_sharded_status_store
from fish_async_task._rust import is_rust_available
from fish_async_task.task_status import ShardedTaskStatusWithExpiry

# 基线数据路径
BASELINE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "rust_baseline",
    "baseline_data.json",
)


@pytest.fixture(autouse=True)
def check_rust():
    """检查 Rust 是否可用"""
    if not is_rust_available():
        pytest.skip("Rust 扩展不可用")


def load_baseline():
    """加载基线数据"""
    if os.path.exists(BASELINE_FILE):
        with open(BASELINE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


class TestStatusWriteThroughputComparison:
    """状态写入吞吐对比"""

    def test_sequential_write_comparison(self):
        """对比顺序写入吞吐"""
        count = 10000

        # 测试 Rust 实现
        rust_store = get_sharded_status_store(shard_count=16, ttl=3600)
        start = time.time()
        for i in range(count):
            rust_store.update_status(
                f"rust_task_{i}", {"status": "pending", "submit_time": time.time()}
            )
        rust_elapsed = time.time() - start
        rust_throughput = count / rust_elapsed

        # 测试 Python 实现
        python_store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)
        start = time.time()
        for i in range(count):
            python_store.update_status(
                f"python_task_{i}", {"status": "pending", "submit_time": time.time()}
            )
        python_elapsed = time.time() - start
        python_throughput = count / python_elapsed

        # 计算加速比
        speedup = rust_throughput / python_throughput if python_throughput > 0 else 0

        print(f"\n[性能对比] 顺序写入吞吐:")
        print(f"  Rust:   {rust_throughput:.0f} ops/s ({rust_elapsed:.3f}s)")
        print(f"  Python: {python_throughput:.0f} ops/s ({python_elapsed:.3f}s)")
        print(f"  加速比: {speedup:.2f}x")

        # Rust 实现应该更快或相当
        assert speedup >= 0.8, f"Rust 实现性能不应该低于 Python 的 80%"

    def test_concurrent_write_comparison(self):
        """对比并发写入吞吐（16 线程）"""
        count = 10000
        num_threads = 16
        items_per_thread = count // num_threads

        def rust_write(thread_id: int):
            rust_store = get_sharded_status_store(shard_count=16, ttl=3600)
            start = time.time()
            for i in range(items_per_thread):
                rust_store.update_status(
                    f"rust_{thread_id}_{i}", {"status": "pending", "submit_time": time.time()}
                )
            return time.time() - start

        def python_write(thread_id: int):
            python_store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)
            start = time.time()
            for i in range(items_per_thread):
                python_store.update_status(
                    f"python_{thread_id}_{i}", {"status": "pending", "submit_time": time.time()}
                )
            return time.time() - start

        # 测试 Rust 实现
        start = time.time()
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            rust_futures = [executor.submit(rust_write, i) for i in range(num_threads)]
            rust_times = [f.result() for f in as_completed(rust_futures)]
        rust_elapsed = time.time() - start
        rust_throughput = count / rust_elapsed

        # 测试 Python 实现
        start = time.time()
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            python_futures = [executor.submit(python_write, i) for i in range(num_threads)]
            python_times = [f.result() for f in as_completed(python_futures)]
        python_elapsed = time.time() - start
        python_throughput = count / python_elapsed

        speedup = rust_throughput / python_throughput if python_throughput > 0 else 0

        print(f"\n[性能对比] 并发写入吞吐 ({num_threads} 线程):")
        print(f"  Rust:   {rust_throughput:.0f} ops/s ({rust_elapsed:.3f}s)")
        print(f"  Python: {python_throughput:.0f} ops/s ({python_elapsed:.3f}s)")
        print(f"  加速比: {speedup:.2f}x")


class TestStatusReadLatencyComparison:
    """状态读取延迟对比"""

    def test_sequential_read_comparison(self):
        """对比顺序读取延迟"""
        count = 10000

        # 准备数据
        rust_store = get_sharded_status_store(shard_count=16, ttl=3600)
        python_store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        for i in range(count):
            status = {"status": "completed", "submit_time": time.time(), "result": i}
            rust_store.update_status(f"task_{i}", status)
            python_store.update_status(f"task_{i}", status)

        # 测试 Rust 实现
        latencies = []
        start = time.time()
        for i in range(count):
            s = time.time()
            rust_store.get_status(f"task_{i}")
            latencies.append((time.time() - s) * 1000)
        rust_elapsed = time.time() - start
        latencies.sort()
        rust_p99 = latencies[int(len(latencies) * 0.99)]
        rust_avg = sum(latencies) / len(latencies)

        # 测试 Python 实现
        latencies = []
        start = time.time()
        for i in range(count):
            s = time.time()
            python_store.get_status(f"task_{i}")
            latencies.append((time.time() - s) * 1000)
        python_elapsed = time.time() - start
        latencies.sort()
        python_p99 = latencies[int(len(latencies) * 0.99)]
        python_avg = sum(latencies) / len(latencies)

        # 计算改进
        avg_improvement = python_avg / rust_avg if rust_avg > 0 else 0
        p99_improvement = python_p99 / rust_p99 if rust_p99 > 0 else 0

        print(f"\n[性能对比] 顺序读取延迟:")
        print(f"  Rust:   平均 {rust_avg:.4f}ms, P99 {rust_p99:.4f}ms")
        print(f"  Python: 平均 {python_avg:.4f}ms, P99 {python_p99:.4f}ms")
        print(f"  改进:  平均 {avg_improvement:.2f}x, P99 {p99_improvement:.2f}x")

    def test_concurrent_read_comparison(self):
        """对比并发读取延迟"""
        count = 10000
        num_threads = 100

        # 准备数据
        rust_store = get_sharded_status_store(shard_count=16, ttl=3600)
        python_store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        for i in range(count):
            status = {"status": "completed", "submit_time": time.time(), "result": i}
            rust_store.update_status(f"task_{i}", status)
            python_store.update_status(f"task_{i}", status)

        def rust_read(thread_id: int):
            reads_per_thread = count // num_threads
            latencies = []
            for i in range(reads_per_thread):
                s = time.time()
                rust_store.get_status(f"task_{thread_id * reads_per_thread + i}")
                latencies.append((time.time() - s) * 1000)
            return latencies

        def python_read(thread_id: int):
            reads_per_thread = count // num_threads
            latencies = []
            for i in range(reads_per_thread):
                s = time.time()
                python_store.get_status(f"task_{thread_id * reads_per_thread + i}")
                latencies.append((time.time() - s) * 1000)
            return latencies

        # 测试 Rust 实现
        start = time.time()
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(rust_read, i) for i in range(num_threads)]
            all_latencies = []
            for f in as_completed(futures):
                all_latencies.extend(f.result())
        rust_elapsed = time.time() - start
        all_latencies.sort()
        rust_p99 = all_latencies[int(len(all_latencies) * 0.99)]

        # 测试 Python 实现
        start = time.time()
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(python_read, i) for i in range(num_threads)]
            all_latencies = []
            for f in as_completed(futures):
                all_latencies.extend(f.result())
        python_elapsed = time.time() - start
        all_latencies.sort()
        python_p99 = all_latencies[int(len(all_latencies) * 0.99)]

        rust_qps = count / rust_elapsed
        python_qps = count / python_elapsed

        print(f"\n[性能对比] 并发读取 ({num_threads} 线程):")
        print(f"  Rust:   {rust_qps:.0f} QPS, P99 {rust_p99:.4f}ms")
        print(f"  Python: {python_qps:.0f} QPS, P99 {python_p99:.4f}ms")


class TestMemoryUsageComparison:
    """内存使用对比

    双口径测量：
    - tracemalloc：只统计 Python 分配器管理的堆内存。Rust 实现的数据
      存储在 Rust 侧堆上，不在其视野内，因此 Rust 的 tracemalloc 数字
      接近 0 是测量盲区，不代表真实内存占用。
    - RSS 差值：进程常驻内存的前后差，跨语言可比，但受分配器缓存、
      页对齐等噪声影响，适合看量级而非精确值。
    """

    @staticmethod
    def _rss_kb() -> float:
        """当前进程 RSS（KB）"""
        import psutil

        return psutil.Process().memory_info().rss / 1024

    def test_status_storage_memory(self):
        """对比状态存储的内存占用（tracemalloc + RSS 双口径）"""
        import gc
        import tracemalloc

        count = 5000

        # 测试 Rust 实现
        gc.collect()
        rss_before_rust = self._rss_kb()
        tracemalloc.start()
        rust_store = get_sharded_status_store(shard_count=16, ttl=3600)
        for i in range(count):
            rust_store.update_status(f"task_{i}", {"status": "pending", "submit_time": time.time()})
        rust_memory = tracemalloc.get_traced_memory()[0] / 1024  # KB
        tracemalloc.stop()
        gc.collect()
        rust_rss_delta = self._rss_kb() - rss_before_rust

        # 测试 Python 实现
        gc.collect()
        rss_before_python = self._rss_kb()
        tracemalloc.start()
        python_store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)
        for i in range(count):
            python_store.update_status(
                f"task_{i}", {"status": "pending", "submit_time": time.time()}
            )
        python_memory = tracemalloc.get_traced_memory()[0] / 1024  # KB
        tracemalloc.stop()
        gc.collect()
        python_rss_delta = self._rss_kb() - rss_before_python

        per_entry_rust = rust_memory / count
        per_entry_python = python_memory / count

        print(f"\n[性能对比] 内存占用 ({count} 条目):")
        print(f"  -- tracemalloc 口径（仅 Python 堆，Rust 侧分配不可见）--")
        print(f"  Rust:   {rust_memory:.1f} KB ({per_entry_rust:.2f} Bytes/条目)")
        print(f"  Python: {python_memory:.1f} KB ({per_entry_python:.2f} Bytes/条目)")
        print(f"  -- RSS 差值口径（跨语言可比，含分配器噪声）--")
        print(f"  Rust:   {rust_rss_delta:.1f} KB ({rust_rss_delta * 1024 / count:.1f} Bytes/条目)")
        print(f"  Python: {python_rss_delta:.1f} KB ({python_rss_delta * 1024 / count:.1f} Bytes/条目)")

        # 功能性 sanity：数据确实写入了两个存储
        assert rust_store.get_total_count() == count
        assert python_store.get_total_count() == count

        # 注意：不对 RSS 差值做硬断言——套件中其他测试先运行时，
        # 分配器会复用已有内存页，RSS 差值可能为 0 甚至为负。
        # 单独运行本测试时 RSS 口径可稳定观测到 Rust 侧的真实占用
        # （约 400 Bytes/条目），证明 tracemalloc 的 ~0 是盲区假象。

        # 保持引用，避免提前被 GC 影响测量
        del rust_store, python_store


class TestPriorityQueueComparison:
    """优先级队列性能对比"""

    def test_queue_operations(self):
        """对比队列操作性能"""
        count = 10000

        # 测试 Rust 实现
        rust_queue = get_priority_queue(maxsize=100000)
        start = time.time()
        for i in range(count):
            rust_queue.put(f"rust_task_{i}", priority=i % 100)
        rust_put_time = time.time() - start

        start = time.time()
        for _ in range(count):
            rust_queue.get(block=False)
        rust_get_time = time.time() - start

        # 测试 Python 实现
        from fish_async_task.performance.priority_queue import PrioritizedTask, PriorityTaskQueue

        python_queue = PriorityTaskQueue(maxsize=100000)
        import time as time_module

        start = time.time()
        for i in range(count):
            task = PrioritizedTask(
                priority=i % 100,
                task_id=f"python_task_{i}",
                func=lambda: None,
                args=(),
                kwargs={},
                submit_time=time_module.time(),
            )
            python_queue.put(task)
        python_put_time = time.time() - start

        start = time.time()
        for _ in range(count):
            python_queue.get(block=False)
        python_get_time = time.time() - start

        put_speedup = python_put_time / rust_put_time if rust_put_time > 0 else 0
        get_speedup = python_get_time / rust_get_time if rust_get_time > 0 else 0

        print(f"\n[性能对比] 优先级队列 ({count} 操作):")
        print(f"  Put 操作:")
        print(f"    Rust:   {rust_put_time:.3f}s ({count/rust_put_time:.0f} ops/s)")
        print(f"    Python: {python_put_time:.3f}s ({count/python_put_time:.0f} ops/s)")
        print(f"    加速比: {put_speedup:.2f}x")
        print(f"  Get 操作:")
        print(f"    Rust:   {rust_get_time:.3f}s ({count/rust_get_time:.0f} ops/s)")
        print(f"    Python: {python_get_time:.3f}s ({count/python_get_time:.0f} ops/s)")
        print(f"    加速比: {get_speedup:.2f}x")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
