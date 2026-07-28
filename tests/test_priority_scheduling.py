"""
TaskManager 优先级调度集成测试

验证 submit_task 的 priority 参数端到端生效：
- priority 是保留关键字参数，不透传给任务函数
- 高优先级任务先于低优先级执行
- 队列满抛 TaskQueueFullError
- shutdown 后 worker 正常退出
"""

import threading
import time

import pytest

from fish_async_task import TaskManager, TaskQueueFullError


@pytest.fixture(autouse=True)
def cleanup_instances():
    """每个测试前后清理单例实例"""
    TaskManager._instances.clear()
    yield
    for instance in list(TaskManager._instances.values()):
        try:
            instance.shutdown()
        except Exception:
            pass
    TaskManager._instances.clear()


def wait_for_completion(manager, task_ids, timeout=15.0):
    """轮询等待所有任务完成，返回 {task_id: status}"""
    deadline = time.monotonic() + timeout
    results = {}
    pending = set(task_ids)
    while pending and time.monotonic() < deadline:
        for tid in list(pending):
            status = manager.get_task_status(tid)
            if status and status["status"] in ("completed", "failed"):
                results[tid] = status
                pending.discard(tid)
        time.sleep(0.05)
    return results


@pytest.mark.timeout(60)
class TestPriorityScheduling:
    """优先级调度端到端行为"""

    def test_priority_param_not_passed_to_task_func(self):
        """priority 是保留参数：任务函数无 priority 形参也不报 TypeError"""
        manager = TaskManager(instance_key="prio_reserved")

        def task_without_priority_param(value):
            return value * 2

        task_id = manager.submit_task(task_without_priority_param, 21, priority=1)
        results = wait_for_completion(manager, [task_id])

        assert results[task_id]["status"] == "completed", (
            f"任务应成功完成（priority 不透传），实际: {results[task_id]}"
        )
        assert results[task_id]["result"] == 42

    def test_priority_ordering_end_to_end(self):
        """单 worker 下，高优先级任务先执行"""
        manager = TaskManager(instance_key="prio_order")
        gate = threading.Event()
        execution_order = []
        order_lock = threading.Lock()

        def blocker():
            gate.wait(timeout=30)
            return "unblocked"

        def record(tag):
            with order_lock:
                execution_order.append(tag)
            return tag

        # 初始只有 1 个 worker（min_workers=1）；扩容检查有 0.1s 延迟 +
        # 5s 冷却，先占住唯一 worker，随后乱序提交三个优先级任务
        blocker_id = manager.submit_task(blocker)
        time.sleep(0.3)  # 确保 blocker 已被 worker 取走

        manager.submit_task(record, "p10", priority=10)
        manager.submit_task(record, "p1", priority=1)
        manager.submit_task(record, "p5", priority=5)
        time.sleep(0.2)  # 确保三个任务都已入队
        gate.set()

        deadline = time.monotonic() + 20
        while len(execution_order) < 3 and time.monotonic() < deadline:
            time.sleep(0.05)

        assert execution_order == ["p1", "p5", "p10"], (
            f"应按优先级顺序执行，实际: {execution_order}"
        )
        # blocker 也应完成
        results = wait_for_completion(manager, [blocker_id])
        assert results[blocker_id]["status"] == "completed"

    def test_default_priority_fifo(self):
        """未指定优先级的任务保持提交顺序（近似 FIFO）"""
        manager = TaskManager(instance_key="prio_fifo")
        gate = threading.Event()
        execution_order = []
        order_lock = threading.Lock()

        def blocker():
            gate.wait(timeout=30)

        def record(tag):
            with order_lock:
                execution_order.append(tag)

        manager.submit_task(blocker)
        time.sleep(0.3)

        for i in range(5):
            manager.submit_task(record, f"t{i}")
            time.sleep(0.01)  # 保证 submit_time 可区分
        gate.set()

        deadline = time.monotonic() + 20
        while len(execution_order) < 5 and time.monotonic() < deadline:
            time.sleep(0.05)

        assert execution_order == ["t0", "t1", "t2", "t3", "t4"], (
            f"默认优先级下应保持提交顺序，实际: {execution_order}"
        )

    def test_invalid_priority_rejected(self):
        """越界 priority 抛 ValueError"""
        manager = TaskManager(instance_key="prio_invalid")

        with pytest.raises(ValueError):
            manager.submit_task(lambda: None, priority=-1)

        with pytest.raises(ValueError):
            manager.submit_task(lambda: None, priority=2**31 - 1)  # 哨兵保留值

        with pytest.raises(ValueError):
            manager.submit_task(lambda: None, priority="high")  # type: ignore[arg-type]

    def test_queue_full_raises(self):
        """队列满 → TaskQueueFullError"""

        class SmallQueueManager(TaskManager):
            DEFAULT_QUEUE_SIZE = 2

        manager = SmallQueueManager(instance_key="prio_full")
        gate = threading.Event()

        def blocker():
            gate.wait(timeout=30)

        try:
            # 占满 worker + 队列（提交足够多的阻塞任务）
            with pytest.raises(TaskQueueFullError):
                for _ in range(100):
                    manager.submit_task(blocker)
        finally:
            gate.set()

    def test_shutdown_exits_workers(self):
        """shutdown 后 worker 全部退出"""
        manager = TaskManager(instance_key="prio_shutdown")

        task_id = manager.submit_task(lambda: "done")
        wait_for_completion(manager, [task_id])

        manager.shutdown()

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            alive = [t for t in manager.worker_threads if t.is_alive()]
            if not alive:
                break
            time.sleep(0.1)
        assert not [t for t in manager.worker_threads if t.is_alive()], (
            "shutdown 后不应有存活的 worker 线程"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
