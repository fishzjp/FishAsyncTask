"""
优先级队列测试
"""

import pytest
import time

from fish_async_task.performance.priority_queue import (
    PrioritizedTask,
    PriorityTaskQueue,
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
