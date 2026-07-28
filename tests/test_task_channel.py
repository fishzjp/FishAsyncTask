"""
TaskChannel 单元测试

TaskChannel 包装优先级队列 + 任务载荷旁路表，向 worker 提供与
queue.Queue 兼容的接口（get/put/put_nowait/qsize/empty/full/task_done）。
"""

import queue
import time

import pytest

from fish_async_task.task_channel import TaskChannel


def make_task(task_id: str):
    """构造 TaskTuple"""
    return (task_id, lambda: task_id, (), {})


@pytest.mark.timeout(20)
class TestTaskChannel:
    """TaskChannel 基础行为"""

    def test_put_get_roundtrip(self):
        """put_task/get 往返，载荷完整"""
        ch = TaskChannel(maxsize=10)
        task = make_task("t1")
        ch.put_task(task)

        result = ch.get(block=False)
        assert result == task

    def test_priority_ordering(self):
        """高优先级（数字小）先出队"""
        ch = TaskChannel(maxsize=10)
        ch.put_task(make_task("low"), priority=10)
        ch.put_task(make_task("high"), priority=1)
        ch.put_task(make_task("mid"), priority=5)

        assert ch.get(block=False)[0] == "high"
        assert ch.get(block=False)[0] == "mid"
        assert ch.get(block=False)[0] == "low"

    def test_get_empty_nonblocking_raises(self):
        """空 + 非阻塞 → queue.Empty"""
        ch = TaskChannel(maxsize=10)
        with pytest.raises(queue.Empty):
            ch.get(block=False)

    def test_get_empty_timeout_raises(self):
        """空 + timeout → queue.Empty"""
        ch = TaskChannel(maxsize=10)
        start = time.monotonic()
        with pytest.raises(queue.Empty):
            ch.get(block=True, timeout=0.3)
        assert time.monotonic() - start >= 0.2

    def test_sentinel_returns_none(self):
        """put_nowait(None) 哨兵 → get 返回 None（关闭信号）"""
        ch = TaskChannel(maxsize=10)
        ch.put_nowait(None)
        assert ch.get(block=False) is None

    def test_sentinel_has_lowest_priority(self):
        """哨兵排在存量任务之后（先清任务再退出）"""
        ch = TaskChannel(maxsize=10)
        ch.put_task(make_task("t1"), priority=100)
        ch.put_nowait(None)

        assert ch.get(block=False)[0] == "t1"
        assert ch.get(block=False) is None

    def test_put_task_full_raises_and_rolls_back(self):
        """满时 put_task → queue.Full，且旁路表回滚不残留"""
        ch = TaskChannel(maxsize=1)
        ch.put_task(make_task("t1"))

        with pytest.raises(queue.Full):
            ch.put_task(make_task("t2"), block=False)

        assert len(ch._payloads) == 1  # 只有 t1

    def test_queue_queue_compat_interface(self):
        """qsize/empty/full/task_done 接口兼容"""
        ch = TaskChannel(maxsize=2)
        assert ch.qsize() == 0
        assert ch.empty() is True
        assert ch.full() is False

        ch.put_task(make_task("t1"))
        ch.put_task(make_task("t2"))
        assert ch.qsize() == 2
        assert ch.full() is True

        ch.task_done()  # 不抛异常即可

    def test_put_none_via_put(self):
        """put(None) 哨兵路径（send_shutdown_signals 的重试分支用 put）"""
        ch = TaskChannel(maxsize=10)
        ch.put(None, timeout=1.0)
        assert ch.get(block=False) is None

    def test_clear_resets_channel(self):
        """clear() 后 qsize 归零，get 不返回孤儿"""
        ch = TaskChannel(maxsize=10)
        ch.put_task(make_task("t1"))
        ch.put_task(make_task("t2"))

        ch.clear()
        assert ch.qsize() == 0
        assert len(ch._payloads) == 0
        with pytest.raises(queue.Empty):
            ch.get(block=False)

    def test_orphan_id_respects_deadline(self):
        """孤儿 id（载荷缺失）重试折算剩余超时，总耗时不放大"""
        ch = TaskChannel(maxsize=10)
        # 直接向底层队列塞一个没有载荷的 id，构造孤儿
        ch._queue.put("orphan_id", priority=1, block=False)

        start = time.monotonic()
        with pytest.raises(queue.Empty):
            ch.get(block=True, timeout=0.5)
        elapsed = time.monotonic() - start
        assert elapsed <= 1.0, f"孤儿重试不应放大超时，实际 {elapsed:.3f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
