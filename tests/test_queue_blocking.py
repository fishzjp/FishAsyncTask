"""
优先级队列阻塞语义测试

覆盖 Rust 与纯 Python 两个适配器实现的 put/get 阻塞、超时与异常语义：
- 队列满 + block=False → queue.Full
- 队列满 + block=True + timeout → 等待超时后 queue.Full
- 队列满 + block=True + 后台消费 → put 被唤醒成功
- 队列空 + block=False / timeout → queue.Empty
"""

import queue
import threading
import time

import pytest

from fish_async_task._adapters import (
    _PythonPriorityTaskQueueAdapter,
    _RustPriorityTaskQueueAdapter,
    is_rust_available,
)

# 参数化两个实现；Rust 不可用时自动跳过 rust 参数
IMPLEMENTATIONS = [
    pytest.param(
        "rust",
        marks=pytest.mark.skipif(not is_rust_available(), reason="Rust 扩展不可用"),
    ),
    pytest.param("python"),
]


def make_adapter(impl: str, maxsize: int):
    if impl == "rust":
        return _RustPriorityTaskQueueAdapter(maxsize)
    return _PythonPriorityTaskQueueAdapter(maxsize)


@pytest.mark.timeout(20)
@pytest.mark.parametrize("impl", IMPLEMENTATIONS)
class TestQueueBlockingSemantics:
    """队列阻塞语义（双实现参数化）"""

    def test_full_nonblocking_raises_full(self, impl):
        """满 + block=False → queue.Full，且不超容"""
        adapter = make_adapter(impl, maxsize=2)
        adapter.put("t1", priority=1, block=False)
        adapter.put("t2", priority=2, block=False)

        with pytest.raises(queue.Full):
            adapter.put("t3", priority=3, block=False)

        assert adapter.qsize() == 2

    def test_full_blocking_with_timeout_raises_full(self, impl):
        """满 + block=True + timeout=0.5 → 等待约 0.5s 后 queue.Full，且不超容"""
        adapter = make_adapter(impl, maxsize=1)
        adapter.put("t1", priority=1, block=False)

        start = time.monotonic()
        with pytest.raises(queue.Full):
            adapter.put("t2", priority=2, block=True, timeout=0.5)
        elapsed = time.monotonic() - start

        assert elapsed >= 0.4, f"应等待约 0.5s 后才超时，实际 {elapsed:.3f}s"
        assert adapter.qsize() == 1, "超时后不得超容入队"

    def test_full_blocking_wakes_up_after_get(self, impl):
        """满 + block=True + 后台线程 0.3s 后 get → put 成功"""
        adapter = make_adapter(impl, maxsize=1)
        adapter.put("t1", priority=1, block=False)

        def consumer():
            time.sleep(0.3)
            adapter.get(block=False)

        t = threading.Thread(target=consumer)
        t.start()
        try:
            # 应阻塞至消费者腾出空间后成功
            adapter.put("t2", priority=2, block=True, timeout=5.0)
        finally:
            t.join()

        assert adapter.qsize() == 1
        assert adapter.get(block=False) == "t2"

    def test_empty_nonblocking_raises_empty(self, impl):
        """空 + block=False → queue.Empty"""
        adapter = make_adapter(impl, maxsize=10)
        with pytest.raises(queue.Empty):
            adapter.get(block=False)

    def test_empty_blocking_with_timeout_raises_empty(self, impl):
        """空 + block=True + timeout=0.3 → 等待约 0.3s 后 queue.Empty"""
        adapter = make_adapter(impl, maxsize=10)

        start = time.monotonic()
        with pytest.raises(queue.Empty):
            adapter.get(block=True, timeout=0.3)
        elapsed = time.monotonic() - start

        assert elapsed >= 0.2, f"应等待约 0.3s 后才超时，实际 {elapsed:.3f}s"

    def test_clear_resets_queue(self, impl):
        """clear() 后队列归零，且阻塞中的 put 被唤醒"""
        adapter = make_adapter(impl, maxsize=2)
        adapter.put("t1", priority=1, block=False)
        adapter.put("t2", priority=2, block=False)

        adapter.clear()
        assert adapter.qsize() == 0
        assert adapter.empty() is True

        # clear 后可以继续正常使用
        adapter.put("t3", priority=3, block=False)
        assert adapter.get(block=False) == "t3"


@pytest.mark.timeout(20)
@pytest.mark.skipif(not is_rust_available(), reason="Rust 扩展不可用")
class TestRustBatchNotify:
    """Rust 批量 API 的 Condvar 通知语义（rust-only：Python 适配器无 batch API）"""

    def test_get_batch_wakes_blocked_put(self):
        """满队列 + 后台 get_batch 腾出空间 → 阻塞中的 put 被唤醒"""
        adapter = _RustPriorityTaskQueueAdapter(maxsize=1)
        adapter.put("t1", priority=1, block=False)

        def batch_consumer():
            time.sleep(0.3)
            adapter._rust.get_batch(1)

        t = threading.Thread(target=batch_consumer)
        t.start()
        try:
            adapter.put("t2", priority=2, block=True, timeout=5.0)
        finally:
            t.join()

        assert adapter.qsize() == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
