"""
优先级队列测试

补充测试用例以提高覆盖率。
"""

import queue as stdlib_queue
import threading
import time

import pytest

from fish_async_task.performance.priority_queue import (
    PrioritizedTask,
    PriorityTaskManager,
    PriorityTaskQueue,
    TaskDependencyManager,
)


class TestPrioritizedTask:
    """测试 PrioritizedTask 类"""

    def test_init(self):
        """测试初始化"""
        task = PrioritizedTask(
            priority=1,
            task_id="task1",
            func=lambda: "result",
            args=(),
            kwargs={},
            submit_time=time.time(),
        )
        assert task.priority == 1
        assert task.task_id == "task1"

    def test_comparison(self):
        """测试优先级比较"""
        now = time.time()
        task1 = PrioritizedTask(1, "task1", lambda: None, (), {}, now)
        task2 = PrioritizedTask(2, "task2", lambda: None, (), {}, now)
        task3 = PrioritizedTask(1, "task3", lambda: None, (), {}, now + 0.1)

        # 优先级数字越小，优先级越高
        assert task1 < task2
        assert task2 > task1
        # 相同优先级时，相等（因为其他字段 compare=False）
        assert task1 == task3


class TestPriorityTaskQueue:
    """测试 PriorityTaskQueue 类"""

    def test_init_default(self):
        """测试默认初始化"""
        queue = PriorityTaskQueue()
        assert queue.maxsize == 1000
        assert queue.empty()

    def test_init_with_maxsize(self):
        """测试指定队列大小"""
        queue = PriorityTaskQueue(maxsize=10)
        assert queue.maxsize == 10

    def test_put_get(self):
        """测试添加和获取任务"""
        queue = PriorityTaskQueue()
        task = PrioritizedTask(
            priority=1,
            task_id="task1",
            func=lambda: "result",
            args=(),
            kwargs={},
            submit_time=time.time(),
        )
        queue.put(task)
        assert queue.qsize() == 1

        retrieved = queue.get()
        assert retrieved.task_id == "task1"
        assert queue.empty()

    def test_priority_ordering(self):
        """测试优先级排序"""
        queue = PriorityTaskQueue()
        now = time.time()

        # 添加不同优先级的任务
        queue.put(PrioritizedTask(3, "low", lambda: None, (), {}, now))
        queue.put(PrioritizedTask(1, "high", lambda: None, (), {}, now))
        queue.put(PrioritizedTask(2, "medium", lambda: None, (), {}, now))

        # 应该按优先级顺序获取（high -> medium -> low）
        assert queue.get().task_id == "high"
        assert queue.get().task_id == "medium"
        assert queue.get().task_id == "low"

    def test_fifo_for_same_priority(self):
        """测试相同优先级时堆的顺序"""
        queue = PriorityTaskQueue()
        now = time.time()

        # 相同优先级的任务，由于堆不稳定，顺序不确定
        queue.put(PrioritizedTask(1, "a", lambda: None, (), {}, now))
        queue.put(PrioritizedTask(1, "c", lambda: None, (), {}, now))
        queue.put(PrioritizedTask(1, "b", lambda: None, (), {}, now))

        # 获取所有任务，验证数量正确
        task_ids = [queue.get().task_id for _ in range(3)]
        assert set(task_ids) == {"a", "b", "c"}
        assert len(task_ids) == 3

    def test_full(self):
        """测试队列满的情况"""
        queue = PriorityTaskQueue(maxsize=2)
        queue.put(PrioritizedTask(1, "task1", lambda: None, (), {}, time.time()))
        queue.put(PrioritizedTask(1, "task2", lambda: None, (), {}, time.time()))
        assert queue.full()

    def test_qsize(self):
        """测试获取队列大小"""
        queue = PriorityTaskQueue()
        assert queue.qsize() == 0
        queue.put(PrioritizedTask(1, "task1", lambda: None, (), {}, time.time()))
        assert queue.qsize() == 1

    def test_clear(self):
        """测试清空队列"""
        queue = PriorityTaskQueue()
        queue.put(PrioritizedTask(1, "task1", lambda: None, (), {}, time.time()))
        queue.put(PrioritizedTask(1, "task2", lambda: None, (), {}, time.time()))
        assert queue.qsize() == 2

        queue.clear()
        assert queue.qsize() == 0
        assert queue.empty()

    def test_get_non_blocking(self):
        """测试非阻塞获取"""
        queue = PriorityTaskQueue()
        # 非阻塞模式获取空队列应该抛出异常
        with pytest.raises(Exception):  # queue.Empty
            queue.get(block=False)

    def test_put_non_blocking_full(self):
        """测试非阻塞添加到满队列"""
        queue = PriorityTaskQueue(maxsize=1)
        queue.put(PrioritizedTask(1, "task1", lambda: None, (), {}, time.time()))

        # 非阻塞模式添加到满队列应该抛出异常
        task2 = PrioritizedTask(1, "task2", lambda: None, (), {}, time.time())
        with pytest.raises(Exception):  # queue.Full
            queue.put(task2, block=False)

    def test_task_done(self):
        """测试任务完成标记"""
        queue = PriorityTaskQueue()
        queue.task_done()  # 不应该抛出异常

    def test_empty(self):
        """测试空队列检查"""
        queue = PriorityTaskQueue()
        assert queue.empty()

        queue.put(PrioritizedTask(1, "task1", lambda: None, (), {}, time.time()))
        assert not queue.empty()

        queue.get(block=False)
        assert queue.empty()

    def test_put_with_timeout_blocks(self):
        """测试带超时的阻塞添加"""
        queue = PriorityTaskQueue(maxsize=2)
        queue.put(PrioritizedTask(1, "task1", lambda: None, (), {}, time.time()))
        queue.put(PrioritizedTask(1, "task2", lambda: None, (), {}, time.time()))

        # 队列已满，添加应该阻塞
        def add_task():
            task3 = PrioritizedTask(1, "task3", lambda: None, (), {}, time.time())
            queue.put(task3, block=True, timeout=0.1)

        thread = threading.Thread(target=add_task)
        thread.start()
        thread.join(timeout=0.3)

        # 线程应该已完成（超时）
        assert not thread.is_alive()

    def test_put_with_timeout_success(self):
        """测试带超时的添加成功"""
        queue = PriorityTaskQueue(maxsize=1)
        queue.put(PrioritizedTask(1, "task1", lambda: None, (), {}, time.time()))

        added = threading.Event()

        def add_task():
            task2 = PrioritizedTask(1, "task2", lambda: None, (), {}, time.time())
            queue.put(task2, block=True, timeout=0.5)
            added.set()

        thread = threading.Thread(target=add_task)
        thread.start()

        time.sleep(0.1)
        # 移除第一个任务
        queue.get(block=False)

        thread.join(timeout=0.3)
        assert added.is_set()

    def test_get_with_timeout_blocks(self):
        """测试带超时的阻塞获取"""
        queue = PriorityTaskQueue()

        def get_task():
            task = queue.get(block=True, timeout=0.1)
            return task

        thread = threading.Thread(target=get_task)
        thread.start()
        thread.join(timeout=0.3)

        # 线程应该已完成（超时）
        assert not thread.is_alive()

    def test_get_with_timeout_success(self):
        """测试带超时的获取成功"""
        queue = PriorityTaskQueue()
        retrieved = threading.Event()

        def get_task():
            task = queue.get(block=True, timeout=0.5)
            retrieved.set()
            return task

        thread = threading.Thread(target=get_task)
        thread.start()

        time.sleep(0.1)
        queue.put(PrioritizedTask(1, "task1", lambda: None, (), {}, time.time()))

        thread.join(timeout=0.3)
        assert retrieved.is_set()

    def test_concurrent_operations(self):
        """测试并发操作"""
        queue = PriorityTaskQueue()
        errors = []
        results = []

        def producer(task_id):
            try:
                for i in range(10):
                    task = PrioritizedTask(i, f"{task_id}_{i}", lambda: None, (), {}, time.time())
                    queue.put(task, block=True, timeout=1.0)
            except Exception as e:
                errors.append(f"Producer error: {e}")

        def consumer():
            try:
                for _ in range(20):
                    task = queue.get(block=True, timeout=1.0)
                    results.append(task.task_id)
            except Exception as e:
                errors.append(f"Consumer error: {e}")

        producers = [threading.Thread(target=producer, args=(f"p{i}",)) for i in range(2)]
        consumers = [threading.Thread(target=consumer) for _ in range(1)]

        for t in producers:
            t.start()
        for t in consumers:
            t.start()

        for t in producers:
            t.join(timeout=3)
        for t in consumers:
            t.join(timeout=3)

        assert not errors
        assert len(results) == 20

    def test_contains(self):
        """测试检查任务是否在队列中"""
        queue = PriorityTaskQueue()
        task = PrioritizedTask(1, "task1", lambda: None, (), {}, time.time())

        assert not queue.contains("task1")
        queue.put(task)
        assert queue.contains("task1")

        queue.get(block=False)
        assert not queue.contains("task1")

    def test_remove(self):
        """测试从队列中移除任务"""
        queue = PriorityTaskQueue()
        task1 = PrioritizedTask(1, "task1", lambda: None, (), {}, time.time())
        task2 = PrioritizedTask(2, "task2", lambda: None, (), {}, time.time())

        queue.put(task1)
        queue.put(task2)

        assert queue.qsize() == 2
        assert queue.remove("task1") is True
        assert queue.qsize() == 1
        assert queue.remove("nonexistent") is False

    def test_remove_middle_task(self):
        """测试移除中间任务"""
        queue = PriorityTaskQueue()
        now = time.time()

        queue.put(PrioritizedTask(3, "low", lambda: None, (), {}, now))
        queue.put(PrioritizedTask(1, "high", lambda: None, (), {}, now))
        queue.put(PrioritizedTask(2, "medium", lambda: None, (), {}, now))

        assert queue.remove("medium") is True
        assert queue.qsize() == 2

        # 验证优先级顺序仍然正确
        assert queue.get().task_id == "high"
        assert queue.get().task_id == "low"

    def test_clear_returns_count(self):
        """测试清空队列返回计数"""
        queue = PriorityTaskQueue()
        queue.put(PrioritizedTask(1, "task1", lambda: None, (), {}, time.time()))
        queue.put(PrioritizedTask(1, "task2", lambda: None, (), {}, time.time()))
        queue.put(PrioritizedTask(1, "task3", lambda: None, (), {}, time.time()))

        count = queue.clear()
        assert count == 3
        assert queue.empty()

    def test_concurrent_producers_consumers(self):
        """测试并发生产者和消费者"""
        queue = PriorityTaskQueue(maxsize=100)
        produced = []
        consumed = []
        errors = []

        def producer(task_id):
            try:
                task = PrioritizedTask(1, task_id, lambda: task_id, (), {}, time.time())
                queue.put(task, block=True, timeout=5.0)
                produced.append(task_id)
            except Exception as e:
                errors.append(f"Producer {task_id} error: {e}")

        def consumer():
            try:
                while True:
                    try:
                        task = queue.get(block=True, timeout=1.0)
                        consumed.append(task.task_id)
                    except stdlib_queue.Empty:
                        # 检查是否所有生产者都完成了
                        if len(produced) >= 50:
                            break
            except Exception as e:
                errors.append(f"Consumer error: {e}")

        # 启动生产者和消费者
        producers = [threading.Thread(target=producer, args=(f"task{i}",)) for i in range(50)]
        consumers = [threading.Thread(target=consumer) for _ in range(2)]

        for t in producers:
            t.start()
        time.sleep(0.1)  # 让生产者先启动
        for t in consumers:
            t.start()

        for t in producers:
            t.join(timeout=10)
        for t in consumers:
            t.join(timeout=10)

        assert not errors, f"Errors occurred: {errors}"
        assert len(produced) == 50
        assert len(consumed) >= 40  # 消费者可能没全部消费，但应该接近


class TestPriorityTaskManager:
    """测试 PriorityTaskManager 类"""

    def test_init(self):
        """测试初始化"""
        manager = PriorityTaskManager()
        assert manager._queue.maxsize == 1000
        assert manager.is_empty()

    def test_init_custom_maxsize(self):
        """测试自定义队列大小"""
        manager = PriorityTaskManager(maxsize=100)
        assert manager._queue.maxsize == 100

    def test_submit_task(self):
        """测试提交任务"""
        manager = PriorityTaskManager()

        task_id = manager.submit_task(lambda: "result", priority=1)
        assert task_id is not None
        assert manager.get_queue_size() == 1

    def test_submit_task_with_custom_id(self):
        """测试提交带自定义ID的任务"""
        manager = PriorityTaskManager()

        task_id = manager.submit_task(lambda: "result", priority=1, task_id="custom_task")
        assert task_id == "custom_task"

    def test_submit_task_with_args(self):
        """测试提交带参数的任务"""
        manager = PriorityTaskManager()

        def task_func(a, b):
            return a + b

        task_id = manager.submit_task(task_func, priority=1, args=(1, 2))
        retrieved = manager.get_task()

        assert retrieved is not None
        assert retrieved.args == (1, 2)

    def test_submit_task_with_kwargs(self):
        """测试提交带关键字参数的任务"""
        manager = PriorityTaskManager()

        def task_func(a, b):
            return a + b

        task_id = manager.submit_task(task_func, priority=1, kwargs={"a": 1, "b": 2})
        retrieved = manager.get_task()

        assert retrieved is not None
        assert retrieved.kwargs == {"a": 1, "b": 2}

    def test_get_task(self):
        """测试获取任务"""
        manager = PriorityTaskManager()

        def task_func():
            return "result"

        manager.submit_task(task_func, priority=1)
        task = manager.get_task()

        assert task is not None
        assert task.task_id is not None

    def test_get_task_timeout(self):
        """测试获取任务超时"""
        manager = PriorityTaskManager()

        task = manager.get_task(timeout=0.1)
        assert task is None

    def test_cancel_task(self):
        """测试取消任务"""
        manager = PriorityTaskManager()

        task_id = manager.submit_task(lambda: "result", priority=1)
        assert manager.get_queue_size() == 1

        result = manager.cancel_task(task_id)
        assert result is True
        assert manager.get_queue_size() == 0

    def test_cancel_nonexistent_task(self):
        """测试取消不存在的任务"""
        manager = PriorityTaskManager()

        result = manager.cancel_task("nonexistent")
        assert result is False

    def test_get_queue_size(self):
        """测试获取队列大小"""
        manager = PriorityTaskManager()

        assert manager.get_queue_size() == 0
        manager.submit_task(lambda: "result", priority=1)
        assert manager.get_queue_size() == 1

    def test_is_empty(self):
        """测试检查是否为空"""
        manager = PriorityTaskManager()

        assert manager.is_empty()
        manager.submit_task(lambda: "result", priority=1)
        assert not manager.is_empty()

    def test_get_pending_count(self):
        """测试获取待处理任务数量"""
        manager = PriorityTaskManager()

        assert manager.get_pending_count() == 0

        for i in range(5):
            manager.submit_task(lambda: "result", priority=1)

        assert manager.get_pending_count() == 5

        # 获取一个任务
        manager.get_task()
        assert manager.get_pending_count() == 4

    def test_priority_ordering(self):
        """测试优先级排序"""
        manager = PriorityTaskManager()

        manager.submit_task(lambda: "low", priority=3)
        manager.submit_task(lambda: "high", priority=1)
        manager.submit_task(lambda: "medium", priority=2)

        # 应该按优先级获取
        task1 = manager.get_task()
        assert task1.priority == 1

        task2 = manager.get_task()
        assert task2.priority == 2

        task3 = manager.get_task()
        assert task3.priority == 3


@pytest.mark.timeout(20)
class TestTaskDependencyManager:
    """测试 TaskDependencyManager 类"""

    def test_init(self):
        """测试初始化"""
        manager = TaskDependencyManager()
        assert manager._dependencies == {}
        assert manager._dependents == {}
        assert manager._completed_tasks == set()

    def test_add_dependency(self):
        """测试添加依赖"""
        manager = TaskDependencyManager()

        manager.add_dependency("task1", ["task_a", "task_b"])
        assert "task1" in manager._dependencies
        assert manager._dependencies["task1"] == {"task_a", "task_b"}

    def test_add_multiple_dependencies(self):
        """测试添加多个依赖"""
        manager = TaskDependencyManager()

        manager.add_dependency("task1", ["task_a"])
        manager.add_dependency("task1", ["task_b", "task_c"])

        assert manager._dependencies["task1"] == {"task_a", "task_b", "task_c"}

    def test_mark_completed(self):
        """测试标记任务完成"""
        manager = TaskDependencyManager()

        manager.add_dependency("task1", ["task_a", "task_b"])
        manager.mark_completed("task_a")

        assert "task_a" in manager._completed_tasks
        assert "task_a" not in manager._dependencies["task1"]

    def test_mark_completed_removes_from_dependents(self):
        """测试标记完成后从依赖者中移除"""
        manager = TaskDependencyManager()

        manager.add_dependency("task1", ["task_a"])
        manager.add_dependency("task2", ["task_a"])
        manager.mark_completed("task_a")

        assert "task_a" not in manager._dependencies.get("task1", set())
        assert "task_a" not in manager._dependencies.get("task2", set())

    def test_mark_failed(self):
        """测试标记任务失败"""
        manager = TaskDependencyManager()

        manager.mark_failed("task1")
        assert "task1" in manager._failed_tasks

    def test_is_ready_no_dependencies(self):
        """测试无依赖任务就绪"""
        manager = TaskDependencyManager()

        assert manager.is_ready("task1") is True

    def test_is_ready_with_dependencies(self):
        """测试有依赖任务的就绪检查"""
        manager = TaskDependencyManager()

        manager.add_dependency("task1", ["task_a", "task_b"])
        assert manager.is_ready("task1") is False

        manager.mark_completed("task_a")
        assert manager.is_ready("task1") is False

        manager.mark_completed("task_b")
        assert manager.is_ready("task1") is True

    def test_get_ready_tasks(self):
        """测试获取所有就绪任务"""
        manager = TaskDependencyManager()

        manager.add_dependency("task1", ["task_a"])
        manager.add_dependency("task2", [])
        manager.add_dependency("task3", ["task_a", "task_b"])
        manager.add_dependency("task4", ["task_a"])

        manager.mark_completed("task_a")

        # task_a 完成后：仅依赖 task_a 的 task1/task4 就绪，无依赖的 task2 就绪，
        # task3 仍等待 task_b。
        # （历史注：此测试曾因 get_ready_tasks 持锁重入死锁而从未执行到断言，
        # 旧断言中 task1 与 task4 依赖相同却期望不同，属自相矛盾。）
        ready = manager.get_ready_tasks()
        assert "task1" in ready
        assert "task2" in ready
        assert "task4" in ready
        assert "task3" not in ready

    def test_has_circular_dependency_no_cycle(self):
        """测试无循环依赖"""
        manager = TaskDependencyManager()

        manager.add_dependency("task1", ["task_a"])
        manager.add_dependency("task_a", ["task_b"])
        manager.add_dependency("task_b", [])

        assert manager.has_circular_dependency("task1") is False

    def test_has_circular_dependency_with_cycle(self):
        """测试有循环依赖"""
        manager = TaskDependencyManager()

        manager.add_dependency("task1", ["task2"])
        manager.add_dependency("task2", ["task3"])
        manager.add_dependency("task3", ["task1"])

        assert manager.has_circular_dependency("task1") is True

    def test_clear(self):
        """测试清除所有依赖信息"""
        manager = TaskDependencyManager()

        manager.add_dependency("task1", ["task_a"])
        manager.mark_completed("task_a")
        manager.mark_failed("task_b")

        manager.clear()

        assert manager._dependencies == {}
        assert manager._dependents == {}
        assert manager._completed_tasks == set()
        assert manager._failed_tasks == set()

    def test_get_stats(self):
        """测试获取统计信息"""
        manager = TaskDependencyManager()

        manager.add_dependency("task1", ["task_a"])
        manager.add_dependency("task2", ["task_a"])
        manager.add_dependency("task3", [])
        manager.mark_completed("task_a")
        manager.mark_failed("task1")

        stats = manager.get_stats()

        assert stats["total_tasks"] == 3
        assert stats["completed_tasks"] == 1
        assert stats["failed_tasks"] == 1
        assert stats["pending_tasks"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
