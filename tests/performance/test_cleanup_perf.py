"""
优先级队列清理性能基准测试

对比全量扫描 vs 优先级队列清理的性能差异
"""

import time

import pytest

from fish_async_task.performance import TaskStatusWithExpiry
from fish_async_task.types import TaskStatusDict


class FullScanCleanup:
    """全量扫描实现（用于对比）"""

    def __init__(self, ttl: int = 300):
        """初始化"""
        self.ttl = ttl
        self.status_dict = {}

    def add_task(self, task_id: str, status: TaskStatusDict) -> None:
        """添加任务"""
        self.status_dict[task_id] = status

    def cleanup_expired(self) -> int:
        """全量扫描清理"""
        current_time = time.time()
        expired_tasks = []

        for task_id, status in self.status_dict.items():
            end_time = status.get("end_time", 0)
            if end_time and current_time - end_time > self.ttl:
                expired_tasks.append(task_id)

        for task_id in expired_tasks:
            del self.status_dict[task_id]

        return len(expired_tasks)


class TestCleanupPerformanceBenchmark:
    """优先级队列清理性能基准测试"""

    def test_cleanup_10k_tasks_performance(self):
        """对比清理 10,000 个任务的性能"""
        # 测试全量扫描实现
        full_scan_store = FullScanCleanup(ttl=300)
        current_time = time.time()

        # 添加 10,000 个过期任务
        for i in range(10000):
            status: TaskStatusDict = {
                "task_id": f"task-{i}",
                "status": "completed",
                "submit_time": current_time - 400,
                "end_time": current_time - 350,  # 已过期
            }
            full_scan_store.add_task(f"task-{i}", status)

        # 测量全量扫描清理时间
        start = time.perf_counter()
        full_scan_cleaned = full_scan_store.cleanup_expired()
        full_scan_time = (time.perf_counter() - start) * 1000  # 转换为毫秒

        # 测试优先级队列实现
        priority_store = TaskStatusWithExpiry(ttl=300)

        for i in range(10000):
            status: TaskStatusDict = {
                "task_id": f"task-{i}",
                "status": "completed",
                "submit_time": current_time - 400,
                "end_time": current_time - 350,
            }
            priority_store.add_task(f"task-{i}", status)

        # 测量优先级队列清理时间
        start = time.perf_counter()
        priority_cleaned = priority_store.cleanup_expired()
        priority_time = (time.perf_counter() - start) * 1000

        # 验证清理数量相同
        assert full_scan_cleaned == priority_cleaned == 10000

        # 输出对比结果
        print(f"\n=== 清理 10,000 个任务性能对比 ===")
        print(f"全量扫描: {full_scan_time:.2f}ms")
        print(f"优先级队列: {priority_time:.2f}ms")
        print(f"性能提升: {full_scan_time / priority_time:.1f}x")
        print(f"时间节省: {full_scan_time - priority_time:.2f}ms ({(1 - priority_time / full_scan_time) * 100:.1f}%)")

        # 验证优先级队列更快（至少快 2 倍，或在 50ms 内完成）
        assert priority_time < full_scan_time / 2 or priority_time < 50, \
            f"优先级队列性能不足: {priority_time:.2f}ms vs {full_scan_time:.2f}ms"

    def test_cleanup_incremental_performance(self):
        """测试增量清理性能"""
        store = TaskStatusWithExpiry(ttl=300)
        current_time = time.time()

        # 添加 100,000 个任务
        for i in range(100000):
            status: TaskStatusDict = {
                "task_id": f"task-{i}",
                "status": "completed",
                "submit_time": current_time - 400,
                "end_time": current_time - 350,  # 已过期
            }
            store.add_task(f"task-{i}", status)

        # 测试增量清理性能（每次最多清理 1000 个）
        start = time.perf_counter()
        total_cleaned = 0
        iterations = 0

        while True:
            cleaned = store.cleanup_expired(max_cleanup=1000)
            total_cleaned += cleaned
            iterations += 1
            if cleaned == 0:
                break

        elapsed = time.perf_counter() - start
        avg_time_per_1k = (elapsed / iterations) * 1000  # 毫秒

        print(f"\n=== 增量清理 100,000 个任务 ===")
        print(f"总清理时间: {elapsed * 1000:.2f}ms")
        print(f"迭代次数: {iterations}")
        print(f"每次清理时间（1k 任务）: {avg_time_per_1k:.2f}ms")
        print(f"清理任务总数: {total_cleaned}")

        # 验证所有任务都被清理
        assert total_cleaned == 100000
        assert store.get_task_count() == 0

        # 验证平均每次清理时间 < 20ms
        assert avg_time_per_1k < 20, f"增量清理过慢: {avg_time_per_1k:.2f}ms"

    def test_cleanup_overhead_with_no_expired_tasks(self):
        """测试没有过期任务时的开销"""
        store = TaskStatusWithExpiry(ttl=300)
        current_time = time.time()

        # 添加 10,000 个未过期任务
        for i in range(10000):
            status: TaskStatusDict = {
                "task_id": f"task-{i}",
                "status": "completed",
                "submit_time": current_time,
                "end_time": current_time + 1000,  # 未过期
            }
            store.add_task(f"task-{i}", status)

        # 测量清理时间（应该很快，因为没有任务需要清理）
        start = time.perf_counter()
        cleaned = store.cleanup_expired()
        elapsed = (time.perf_counter() - start) * 1000  # 毫秒

        print(f"\n=== 清理无过期任务的开销 ===")
        print(f"清理时间: {elapsed:.2f}ms")
        print(f"清理数量: {cleaned}")

        # 验证没有任务被清理
        assert cleaned == 0

        # 验证开销很小（< 5ms）
        assert elapsed < 5, f"无过期任务时开销过大: {elapsed:.2f}ms"

    def test_enforce_max_count_performance(self):
        """测试强制执行最大数量限制的性能"""
        store = TaskStatusWithExpiry(ttl=300)
        current_time = time.time()

        # 添加 50,000 个任务
        for i in range(50000):
            status: TaskStatusDict = {
                "task_id": f"task-{i}",
                "status": "completed",
                "submit_time": current_time - (50000 - i) / 1000,  # 不同的时间戳
                "end_time": current_time,
            }
            store.add_task(f"task-{i}", status)

        # 测量强制执行限制的时间
        start = time.perf_counter()
        removed = store.enforce_max_count(max_count=10000)
        elapsed = (time.perf_counter() - start) * 1000  # 毫秒

        print(f"\n=== 强制执行最大数量限制性能 ===")
        print(f"删除数量: {removed}")
        print(f"耗时: {elapsed:.2f}ms")
        print(f"剩余任务: {store.get_task_count()}")

        # 验证删除了正确的数量
        assert removed == 40000
        assert store.get_task_count() == 10000

        # 验证性能合理（< 500ms）
        assert elapsed < 500, f"强制执行限制过慢: {elapsed:.2f}ms"
