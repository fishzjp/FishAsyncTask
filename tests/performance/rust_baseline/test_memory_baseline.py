"""
内存使用基线测试

测试 FishAsyncTask Python 实现的内存使用情况，为 Rust 实现提供对比基准。
"""

import json
import os
import time
import tracemalloc
from typing import Any, Dict

import pytest

from fish_async_task.task_status import ShardedTaskStatusWithExpiry
from fish_async_task.types import TaskStatusDict


BASELINE_FILE = os.path.join(os.path.dirname(__file__), "baseline_memory.json")


def save_memory_baseline(results: Dict[str, Any]) -> None:
    """保存内存基线结果"""
    with open(BASELINE_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n内存基线数据已保存到: {BASELINE_FILE}")


class TestMemoryBaseline:
    """内存使用基线测试"""

    def test_empty_store_memory(self) -> None:
        """测试空存储的内存占用"""
        tracemalloc.start()

        # 创建存储
        store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)
        current, peak = tracemalloc.get_traced_memory()

        tracemalloc.stop()

        results = {
            "test_name": "empty_store_memory",
            "shard_count": 16,
            "current_memory_kb": round(current / 1024, 2),
            "peak_memory_kb": round(peak / 1024, 2),
        }

        print(f"\n[内存基线] 空存储内存占用:")
        print(f"  当前内存: {current / 1024:.2f} KB")
        print(f"  峰值内存: {peak / 1024:.2f} KB")

        save_memory_baseline(results)

    def test_status_entry_memory(self) -> None:
        """测试单个状态条目的内存占用"""
        tracemalloc.start()

        # 创建存储并添加条目
        store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        # 添加 10000 个状态
        count = 10000
        for i in range(count):
            task_id = f"task_{i}"
            status: TaskStatusDict = {
                "status": "pending",
                "submit_time": time.time(),
            }
            store.update_status(task_id, status)

        current, peak = tracemalloc.get_traced_memory()

        tracemalloc.stop()

        per_entry_bytes = current / count
        per_entry_kb = per_entry_bytes / 1024

        results = {
            "test_name": "status_entry_memory",
            "entry_count": count,
            "total_memory_kb": round(current / 1024, 2),
            "peak_memory_kb": round(peak / 1024, 2),
            "per_entry_bytes": round(per_entry_bytes, 2),
            "per_entry_kb": round(per_entry_kb, 4),
        }

        print(f"\n[内存基线] 状态条目内存占用:")
        print(f"  条目数量: {count}")
        print(f"  总内存: {current / 1024:.2f} KB")
        print(f"  峰值内存: {peak / 1024:.2f} KB")
        print(f"  每条目平均: {per_entry_bytes:.2f} Bytes ({per_entry_kb:.4f} KB)")

        save_memory_baseline(results)

    def test_complete_status_memory(self) -> None:
        """测试完整状态（包含所有字段）的内存占用"""
        tracemalloc.start()

        store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        # 添加包含所有字段的完整状态
        count = 10000
        for i in range(count):
            task_id = f"task_{i}"
            status: TaskStatusDict = {
                "status": "completed",
                "submit_time": time.time() - 10,
                "start_time": time.time() - 9,
                "end_time": time.time() - 8,
                "result": i * 2,
                "worker_id": f"worker_{i % 16}",
            }
            store.update_status(task_id, status)

        current, peak = tracemalloc.get_traced_memory()

        tracemalloc.stop()

        per_entry_bytes = current / count

        results = {
            "test_name": "complete_status_memory",
            "entry_count": count,
            "total_memory_kb": round(current / 1024, 2),
            "peak_memory_kb": round(peak / 1024, 2),
            "per_entry_bytes": round(per_entry_bytes, 2),
        }

        print(f"\n[内存基线] 完整状态内存占用:")
        print(f"  条目数量: {count}")
        print(f"  总内存: {current / 1024:.2f} KB")
        print(f"  峰值内存: {peak / 1024:.2f} KB")
        print(f"  每条目平均: {per_entry_bytes:.2f} Bytes")

        save_memory_baseline(results)

    def test_sharding_overhead(self) -> None:
        """测试分片开销：不同分片数的内存占用"""
        count = 5000

        shard_counts = [4, 8, 16, 32, 64]
        results_list = []

        for shard_count in shard_counts:
            tracemalloc.start()

            store = ShardedTaskStatusWithExpiry(shard_count=shard_count, ttl=3600)

            for i in range(count):
                task_id = f"task_{shard_count}_{i}"
                status: TaskStatusDict = {
                    "status": "pending",
                    "submit_time": time.time(),
                }
                store.update_status(task_id, status)

            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            per_entry_bytes = current / count

            result = {
                "shard_count": shard_count,
                "total_memory_kb": round(current / 1024, 2),
                "per_entry_bytes": round(per_entry_bytes, 2),
            }
            results_list.append(result)

            print(f"  分片数 {shard_count}: {current / 1024:.2f} KB 总计, {per_entry_bytes:.2f} Bytes/条目")

        results = {
            "test_name": "sharding_overhead",
            "entry_count": count,
            "results": results_list,
        }

        print(f"\n[内存基线] 分片开销对比:")
        for r in results_list:
            print(
                f"  分片数 {r['shard_count']}: {r['total_memory_kb']} KB 总计, "
                f"{r['per_entry_bytes']} Bytes/条目"
            )

        save_memory_baseline(results)

    def test_expiry_heap_memory(self) -> None:
        """测试过期时间堆的内存占用"""
        tracemalloc.start()

        store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        # 添加已完成任务（会创建过期堆条目）
        count = 10000
        for i in range(count):
            task_id = f"task_{i}"
            status: TaskStatusDict = {
                "status": "completed",
                "submit_time": time.time() - 10,
                "start_time": time.time() - 9,
                "end_time": time.time(),
                "result": i * 2,
            }
            store.update_status(task_id, status)

        current, peak = tracemalloc.get_traced_memory()

        tracemalloc.stop()

        per_entry_bytes = current / count

        results = {
            "test_name": "expiry_heap_memory",
            "entry_count": count,
            "total_memory_kb": round(current / 1024, 2),
            "peak_memory_kb": round(peak / 1024, 2),
            "per_entry_bytes": round(per_entry_bytes, 2),
        }

        print(f"\n[内存基线] 过期堆内存占用:")
        print(f"  条目数量: {count}")
        print(f"  总内存: {current / 1024:.2f} KB")
        print(f"  峰值内存: {peak / 1024:.2f} KB")
        print(f"  每条目平均: {per_entry_bytes:.2f} Bytes")

        save_memory_baseline(results)


def test_generate_full_memory_baseline() -> None:
    """
    生成完整的内存基线报告

    运行所有内存测试并生成综合报告。
    """
    tracemalloc.start()

    # 1. 空存储
    empty_store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)
    empty_current, empty_peak = tracemalloc.get_traced_memory()

    # 2. 基本状态条目
    store = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)
    count = 10000
    for i in range(count):
        store.update_status(f"task_{i}", {"status": "pending", "submit_time": time.time()})
    basic_current, basic_peak = tracemalloc.get_traced_memory()
    basic_overhead = basic_current - empty_current

    # 3. 完整状态
    store_full = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)
    for i in range(count):
        store_full.update_status(
            f"full_{i}",
            {
                "status": "completed",
                "submit_time": time.time() - 10,
                "start_time": time.time() - 9,
                "end_time": time.time(),
                "result": i * 2,
                "worker_id": f"worker_{i % 16}",
            },
        )
    full_current, full_peak = tracemalloc.get_traced_memory()
    full_overhead = full_current - basic_current

    tracemalloc.stop()

    # 综合报告
    full_report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "python_version": f"{__import__('sys').version_info.major}.{__import__('sys').version_info.minor}",
        "summary": {
            "empty_store_overhead_kb": round(empty_current / 1024, 2),
            "basic_status_per_entry_bytes": round(basic_overhead / count, 2),
            "full_status_overhead_kb": round(full_overhead / 1024, 2),
            "full_status_per_entry_bytes": round(full_current / count, 2),
        },
        "detailed": {
            "empty_store": {
                "current_memory_kb": round(empty_current / 1024, 2),
                "peak_memory_kb": round(empty_peak / 1024, 2),
            },
            "basic_status": {
                "entry_count": count,
                "total_memory_kb": round(basic_current / 1024, 2),
                "per_entry_bytes": round(basic_overhead / count, 2),
            },
            "full_status": {
                "entry_count": count,
                "total_memory_kb": round(full_current / 1024, 2),
                "per_entry_bytes": round(full_current / count, 2),
            },
        },
    }

    save_memory_baseline(full_report)

    print(f"\n{'='*50}")
    print(f"[内存基线报告]")
    print(f"空存储开销: {empty_current / 1024:.2f} KB")
    print(f"基本状态: {basic_overhead / count:.2f} Bytes/条目")
    print(f"完整状态: {full_current / count:.2f} Bytes/条目")
    print(f"{'='*50}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
