"""
Python 实现性能基线测试

此模块建立了 FishAsyncTask Python 实现的性能基线，用于后续与 Rust 实现进行对比。

测试场景：
1. 状态写入吞吐 - 测试高并发写入性能
2. 状态读取延迟 - 测试状态查询的 P50/P99 延迟
3. 批量操作性能 - 测试批量读取/更新性能
4. 清理操作性能 - 测试过期任务清理性能
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import pytest

from fish_async_task.task_status import (
    ShardedTaskStatusWithExpiry,
    TaskStatusManager,
)
from fish_async_task.types import TaskStatus, TaskStatusDict

# 基线数据保存路径
BASELINE_FILE = os.path.join(os.path.dirname(__file__), "baseline_data.json")


def save_baseline_results(results: Dict[str, Any]) -> None:
    """
    保存基线测试结果到文件

    Args:
        results: 测试结果字典
    """
    with open(BASELINE_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n基线数据已保存到: {BASELINE_FILE}")


def simple_task(value: int) -> int:
    """简单的测试任务"""
    return value * 2


class TestStatusWriteThroughput:
    """状态写入吞吐测试"""

    def test_sequential_write_throughput(self) -> None:
        """测试顺序写入吞吐"""
        store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        # 测试写入 10,000 条状态
        count = 10000
        start_time = time.time()

        for i in range(count):
            task_id = f"task_{i}"
            status: TaskStatusDict = {
                "status": "pending",
                "submit_time": time.time(),
            }
            store.update_status(task_id, status)

        end_time = time.time()
        elapsed = end_time - start_time
        throughput = count / elapsed

        results = {
            "test_name": "sequential_write_throughput",
            "count": count,
            "elapsed_seconds": round(elapsed, 3),
            "throughput_ops_per_sec": round(throughput, 0),
        }

        print(f"\n[基线] 顺序写入吞吐:")
        print(f"  写入数量: {count}")
        print(f"  耗时: {elapsed:.3f}秒")
        print(f"  吞吐量: {throughput:.0f} ops/s")

        # 保存结果用于后续对比
        if not os.path.exists(BASELINE_FILE):
            baseline = {}
        else:
            with open(BASELINE_FILE, "r", encoding="utf-8") as f:
                baseline = json.load(f)
        baseline["sequential_write_throughput"] = results
        save_baseline_results(baseline)

        # 基线断言
        assert throughput > 0, "吞吐量应该大于 0"

    def test_concurrent_write_throughput(self) -> None:
        """测试并发写入吞吐（16 线程）"""
        store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        # 测试参数
        count = 10000
        num_threads = 16
        items_per_thread = count // num_threads

        def write_items(thread_id: int) -> float:
            """写入一组状态并返回耗时"""
            start = time.time()
            for i in range(items_per_thread):
                task_id = f"task_{thread_id}_{i}"
                status: TaskStatusDict = {
                    "status": "pending",
                    "submit_time": time.time(),
                }
                store.update_status(task_id, status)
            return time.time() - start

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(write_items, i) for i in range(num_threads)]
            thread_times = [f.result() for f in as_completed(futures)]

        end_time = time.time()
        elapsed = end_time - start_time
        throughput = count / elapsed

        results = {
            "test_name": "concurrent_write_throughput",
            "count": count,
            "num_threads": num_threads,
            "elapsed_seconds": round(elapsed, 3),
            "throughput_ops_per_sec": round(throughput, 0),
            "max_thread_time_seconds": round(max(thread_times), 3),
        }

        print(f"\n[基线] 并发写入吞吐 ({num_threads} 线程):")
        print(f"  写入数量: {count}")
        print(f"  耗时: {elapsed:.3f}秒")
        print(f"  吞吐量: {throughput:.0f} ops/s")

        # 保存结果
        if not os.path.exists(BASELINE_FILE):
            baseline = {}
        else:
            with open(BASELINE_FILE, "r", encoding="utf-8") as f:
                baseline = json.load(f)
        baseline["concurrent_write_throughput"] = results
        save_baseline_results(baseline)

        assert throughput > 0


class TestStatusReadLatency:
    """状态读取延迟测试"""

    def test_sequential_read_latency(self) -> None:
        """测试顺序读取延迟"""
        store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        # 准备数据
        count = 10000
        for i in range(count):
            task_id = f"task_{i}"
            status: TaskStatusDict = {
                "status": "completed",
                "submit_time": time.time(),
                "start_time": time.time(),
                "end_time": time.time(),
                "result": i * 2,
            }
            store.update_status(task_id, status)

        # 测试读取延迟
        latencies = []
        start_time = time.time()

        for i in range(count):
            read_start = time.time()
            store.get_status(f"task_{i}")
            latencies.append((time.time() - read_start) * 1000)  # 转换为毫秒

        end_time = time.time()
        elapsed = end_time - start_time

        # 计算统计数据
        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]
        avg = sum(latencies) / len(latencies)

        results = {
            "test_name": "sequential_read_latency",
            "count": count,
            "elapsed_seconds": round(elapsed, 3),
            "avg_latency_ms": round(avg, 4),
            "p50_latency_ms": round(p50, 4),
            "p95_latency_ms": round(p95, 4),
            "p99_latency_ms": round(p99, 4),
        }

        print(f"\n[基线] 顺序读取延迟:")
        print(f"  读取数量: {count}")
        print(f"  平均延迟: {avg:.4f}ms")
        print(f"  P50 延迟: {p50:.4f}ms")
        print(f"  P95 延迟: {p95:.4f}ms")
        print(f"  P99 延迟: {p99:.4f}ms")

        # 保存结果
        if not os.path.exists(BASELINE_FILE):
            baseline = {}
        else:
            with open(BASELINE_FILE, "r", encoding="utf-8") as f:
                baseline = json.load(f)
        baseline["sequential_read_latency"] = results
        save_baseline_results(baseline)

        assert avg > 0

    def test_concurrent_read_latency(self) -> None:
        """测试并发读取延迟"""
        store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        # 准备数据
        count = 10000
        for i in range(count):
            task_id = f"task_{i}"
            status: TaskStatusDict = {
                "status": "completed",
                "submit_time": time.time(),
                "start_time": time.time(),
                "end_time": time.time(),
                "result": i * 2,
            }
            store.update_status(task_id, status)

        # 测试并发读取
        num_threads = 100
        reads_per_thread = count // num_threads

        def read_items(thread_id: int) -> List[float]:
            """读取一组状态并返回延迟"""
            latencies = []
            for i in range(reads_per_thread):
                task_id = f"task_{thread_id * reads_per_thread + i}"
                read_start = time.time()
                store.get_status(task_id)
                latencies.append((time.time() - read_start) * 1000)
            return latencies

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(read_items, i) for i in range(num_threads)]
            all_latencies = []
            for f in as_completed(futures):
                all_latencies.extend(f.result())

        end_time = time.time()
        elapsed = end_time - start_time

        # 计算统计数据
        all_latencies.sort()
        p50 = all_latencies[len(all_latencies) // 2]
        p95 = all_latencies[int(len(all_latencies) * 0.95)]
        p99 = all_latencies[int(len(all_latencies) * 0.99)]
        avg = sum(all_latencies) / len(all_latencies)
        qps = count / elapsed

        results = {
            "test_name": "concurrent_read_latency",
            "count": count,
            "num_threads": num_threads,
            "elapsed_seconds": round(elapsed, 3),
            "qps": round(qps, 0),
            "avg_latency_ms": round(avg, 4),
            "p50_latency_ms": round(p50, 4),
            "p95_latency_ms": round(p95, 4),
            "p99_latency_ms": round(p99, 4),
        }

        print(f"\n[基线] 并发读取延迟 ({num_threads} 线程):")
        print(f"  读取数量: {count}")
        print(f"  QPS: {qps:.0f}")
        print(f"  平均延迟: {avg:.4f}ms")
        print(f"  P50 延迟: {p50:.4f}ms")
        print(f"  P95 延迟: {p95:.4f}ms")
        print(f"  P99 延迟: {p99:.4f}ms")

        # 保存结果
        if not os.path.exists(BASELINE_FILE):
            baseline = {}
        else:
            with open(BASELINE_FILE, "r", encoding="utf-8") as f:
                baseline = json.load(f)
        baseline["concurrent_read_latency"] = results
        save_baseline_results(baseline)

        assert qps > 0


class TestBatchOperations:
    """批量操作性能测试"""

    def test_batch_read_performance(self) -> None:
        """测试批量读取性能（Python 实现使用循环）"""
        store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        # 准备数据
        count = 10000
        task_ids = [f"task_{i}" for i in range(count)]
        for task_id in task_ids:
            status: TaskStatusDict = {
                "status": "completed",
                "submit_time": time.time(),
                "start_time": time.time(),
                "end_time": time.time(),
                "result": 42,
            }
            store.update_status(task_id, status)

        # 模拟批量读取（Python 实现）
        start_time = time.time()
        results = [store.get_status(task_id) for task_id in task_ids]
        end_time = time.time()

        elapsed = end_time - start_time
        throughput = count / elapsed

        results_data = {
            "test_name": "batch_read_performance",
            "count": count,
            "elapsed_seconds": round(elapsed, 3),
            "throughput_ops_per_sec": round(throughput, 0),
        }

        print(f"\n[基线] 批量读取性能:")
        print(f"  读取数量: {count}")
        print(f"  耗时: {elapsed:.3f}秒")
        print(f"  吞吐量: {throughput:.0f} ops/s")

        # 保存结果
        if not os.path.exists(BASELINE_FILE):
            baseline = {}
        else:
            with open(BASELINE_FILE, "r", encoding="utf-8") as f:
                baseline = json.load(f)
        baseline["batch_read_performance"] = results_data
        save_baseline_results(baseline)

        assert len(results) == count
        assert all(r is not None for r in results)

    def test_batch_update_performance(self) -> None:
        """测试批量更新性能（Python 实现）"""
        store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        # 准备批量更新数据
        count = 10000
        updates = [
            (f"task_{i}", {"status": "pending", "submit_time": time.time()}) for i in range(count)
        ]

        # 模拟批量更新（Python 实现）
        start_time = time.time()
        for task_id, status in updates:
            store.update_status(task_id, status)
        end_time = time.time()

        elapsed = end_time - start_time
        throughput = count / elapsed

        results_data = {
            "test_name": "batch_update_performance",
            "count": count,
            "elapsed_seconds": round(elapsed, 3),
            "throughput_ops_per_sec": round(throughput, 0),
        }

        print(f"\n[基线] 批量更新性能:")
        print(f"  更新数量: {count}")
        print(f"  耗时: {elapsed:.3f}秒")
        print(f"  吞吐量: {throughput:.0f} ops/s")

        # 保存结果
        if not os.path.exists(BASELINE_FILE):
            baseline = {}
        else:
            with open(BASELINE_FILE, "r", encoding="utf-8") as f:
                baseline = json.load(f)
        baseline["batch_update_performance"] = results_data
        save_baseline_results(baseline)

        assert store.get_total_count() == count


class TestCleanupPerformance:
    """清理操作性能测试"""

    def test_cleanup_expired_performance(self) -> None:
        """测试过期任务清理性能"""
        store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=1)

        # 准备数据：创建已完成且即将过期的任务
        count = 10000
        now = time.time()
        for i in range(count):
            task_id = f"task_{i}"
            status: TaskStatusDict = {
                "status": "completed",
                "submit_time": now - 10,
                "start_time": now - 9,
                "end_time": now - 8,  # 已完成，由于 TTL=1，已过期
                "result": i * 2,
            }
            store.update_status(task_id, status)

        # 等待确保任务过期
        time.sleep(0.5)

        # 测试清理性能
        start_time = time.time()
        cleaned = store.cleanup_expired(max_cleanup=None)
        end_time = time.time()

        elapsed = end_time - start_time

        results_data = {
            "test_name": "cleanup_expired_performance",
            "total_count": count,
            "cleaned_count": cleaned,
            "elapsed_seconds": round(elapsed, 3),
            "cleanup_rate_ops_per_sec": round(cleaned / elapsed, 0) if elapsed > 0 else 0,
        }

        print(f"\n[基线] 清理过期任务性能:")
        print(f"  总任务数: {count}")
        print(f"  清理数量: {cleaned}")
        print(f"  耗时: {elapsed:.3f}秒")

        # 保存结果
        if not os.path.exists(BASELINE_FILE):
            baseline = {}
        else:
            with open(BASELINE_FILE, "r", encoding="utf-8") as f:
                baseline = json.load(f)
        baseline["cleanup_expired_performance"] = results_data
        save_baseline_results(baseline)

        assert cleaned >= count * 0.9, "应该清理至少 90% 的任务"


def test_generate_full_baseline_report() -> None:
    """
    生成完整的基线测试报告

    运行所有测试并生成综合报告。
    """
    store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

    # 1. 顺序写入吞吐
    count = 10000
    start = time.time()
    for i in range(count):
        store.update_status(f"task_{i}", {"status": "pending", "submit_time": time.time()})
    write_time = time.time() - start
    write_throughput = count / write_time

    # 2. 顺序读取延迟
    latencies = []
    for i in range(count):
        s = time.time()
        store.get_status(f"task_{i}")
        latencies.append((time.time() - s) * 1000)
    latencies.sort()
    read_p50 = latencies[len(latencies) // 2]
    read_p99 = latencies[int(len(latencies) * 0.99)]
    read_avg = sum(latencies) / len(latencies)

    # 3. 清理性能
    store_expire = ShardedTaskStatusWithExpiry(shard_count=16, ttl=1)
    now = time.time()
    for i in range(1000):
        store_expire.update_status(
            f"expire_{i}",
            {
                "status": "completed",
                "submit_time": now - 10,
                "start_time": now - 9,
                "end_time": now - 8,
                "result": i,
            },
        )
    time.sleep(0.5)
    start = time.time()
    cleaned = store_expire.cleanup_expired()
    cleanup_time = time.time() - start

    # 综合报告
    full_report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "python_version": f"{__import__('sys').version_info.major}.{__import__('sys').version_info.minor}",
        "summary": {
            "write_throughput_ops_per_sec": round(write_throughput, 0),
            "read_avg_latency_ms": round(read_avg, 4),
            "read_p50_latency_ms": round(read_p50, 4),
            "read_p99_latency_ms": round(read_p99, 4),
            "cleanup_time_for_1k_tasks_ms": round(cleanup_time * 1000, 2),
        },
        "detailed": {
            "sequential_write": {
                "count": count,
                "elapsed_seconds": round(write_time, 3),
                "throughput_ops_per_sec": round(write_throughput, 0),
            },
            "sequential_read": {
                "count": count,
                "avg_latency_ms": round(read_avg, 4),
                "p50_latency_ms": round(read_p50, 4),
                "p99_latency_ms": round(read_p99, 4),
            },
            "cleanup": {
                "total_count": 1000,
                "cleaned_count": cleaned,
                "elapsed_seconds": round(cleanup_time, 3),
            },
        },
    }

    save_baseline_results(full_report)

    print(f"\n{'='*50}")
    print(f"[完整基线报告]")
    print(f"写入吞吐: {write_throughput:.0f} ops/s")
    print(f"读取延迟 - 平均: {read_avg:.4f}ms, P50: {read_p50:.4f}ms, P99: {read_p99:.4f}ms")
    print(f"清理性能: {cleanup_time*1000:.2f}ms / 1000 任务")
    print(f"{'='*50}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
