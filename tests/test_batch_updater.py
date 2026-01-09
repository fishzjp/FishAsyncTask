"""批量状态更新器测试

测试 BatchedStatusUpdater 类的批量更新、自动刷新、手动刷新等功能。
"""

import time
from typing import Any, Dict

import pytest

from fish_async_task.performance.batch_updater import BatchedStatusUpdater
from fish_async_task.types import TaskStatusDict


class TestBatchedStatusUpdater:
    """测试 BatchedStatusUpdater 类的基本功能"""

    def test_init_default_params(self):
        """测试使用默认参数初始化"""
        updater = BatchedStatusUpdater()

        assert updater.buffer_size == 100
        assert updater.flush_interval == 1.0
        assert updater.get_buffer_length() == 0

    def test_init_custom_params(self):
        """测试使用自定义参数初始化"""
        updater = BatchedStatusUpdater(buffer_size=50, flush_interval=0.5)

        assert updater.buffer_size == 50
        assert updater.flush_interval == 0.5
        assert updater.get_buffer_length() == 0

    def test_queue_single_update(self):
        """测试排队单个更新"""
        mock_store = {}
        updater = BatchedStatusUpdater(underlying_store=mock_store)

        updater.queue_update("task-1", {"status": "running", "progress": 0.5})

        # 验证更新在缓冲区中
        assert updater.get_buffer_length() == 1
        # 验证尚未刷新到底层存储
        assert "task-1" not in mock_store

    def test_queue_multiple_updates(self):
        """测试排队多个更新"""
        mock_store = {}
        updater = BatchedStatusUpdater(buffer_size=5, underlying_store=mock_store)

        # 添加 4 个更新（未达到 buffer_size）
        for i in range(4):
            updater.queue_update(f"task-{i}", {"status": "pending"})

        assert updater.get_buffer_length() == 4
        assert len(mock_store) == 0

    def test_auto_flush_on_buffer_size(self):
        """测试达到 buffer_size 时自动刷新"""
        mock_store = {}
        updater = BatchedStatusUpdater(
            buffer_size=3, flush_interval=1.0, underlying_store=mock_store
        )

        # 添加 3 个更新（达到 buffer_size）
        for i in range(3):
            updater.queue_update(f"task-{i}", {"status": "running"})

        # 验证自动刷新
        assert updater.get_buffer_length() == 0
        assert len(mock_store) == 3
        assert "task-0" in mock_store
        assert "task-1" in mock_store
        assert "task-2" in mock_store

    def test_manual_flush(self):
        """测试手动刷新"""
        mock_store = {}
        updater = BatchedStatusUpdater(
            buffer_size=100, flush_interval=10.0, underlying_store=mock_store
        )

        # 添加 2 个更新（未达到 buffer_size）
        updater.queue_update("task-1", {"status": "pending"})
        updater.queue_update("task-2", {"status": "running"})

        assert updater.get_buffer_length() == 2
        assert len(mock_store) == 0

        # 手动刷新
        flushed = updater.flush()

        assert flushed == 2
        assert updater.get_buffer_length() == 0
        assert len(mock_store) == 2
        assert mock_store["task-1"]["status"] == "pending"
        assert mock_store["task-2"]["status"] == "running"

    def test_auto_flush_on_interval(self):
        """测试达到 flush_interval 时自动刷新"""
        mock_store = {}
        updater = BatchedStatusUpdater(
            buffer_size=100, flush_interval=0.3, underlying_store=mock_store  # 300ms
        )

        # 添加更新（未达到 buffer_size）
        updater.queue_update("task-1", {"status": "pending"})

        assert updater.get_buffer_length() == 1
        assert len(mock_store) == 0

        # 等待超过 flush_interval
        time.sleep(0.4)

        # 添加另一个更新（触发时间检查）
        updater.queue_update("task-2", {"status": "running"})

        # 验证自动刷新（由于时间间隔）
        assert updater.get_buffer_length() == 1  # 只有 task-2
        assert len(mock_store) == 1
        assert "task-1" in mock_store

    def test_flush_empty_buffer(self):
        """测试刷新空缓冲区"""
        mock_store = {}
        updater = BatchedStatusUpdater(underlying_store=mock_store)

        flushed = updater.flush()

        assert flushed == 0
        assert len(mock_store) == 0

    def test_overwrite_same_task_in_buffer(self):
        """测试缓冲区中同一任务的多次更新（覆盖）"""
        mock_store = {}
        updater = BatchedStatusUpdater(buffer_size=10, underlying_store=mock_store)

        # 对同一任务多次更新
        updater.queue_update("task-1", {"status": "pending", "progress": 0.0})
        updater.queue_update("task-1", {"status": "running", "progress": 0.5})
        updater.queue_update("task-1", {"status": "completed", "progress": 1.0})

        # 缓冲区应该只保留最新的更新
        assert updater.get_buffer_length() == 1

        # 刷新后验证只有最新状态
        updater.flush()
        assert mock_store["task-1"]["status"] == "completed"
        assert mock_store["task-1"]["progress"] == 1.0

    def test_update_sync_method(self):
        """测试同步更新方法（立即更新）"""
        mock_store = {}
        updater = BatchedStatusUpdater(underlying_store=mock_store)

        # 使用 update_sync 立即更新
        updater.update_sync("task-1", {"status": "running"})

        # 验证立即写入底层存储
        assert "task-1" in mock_store
        assert mock_store["task-1"]["status"] == "running"
        # 缓冲区应该为空
        assert updater.get_buffer_length() == 0

    def test_flush_on_close(self):
        """测试关闭时刷新待处理更新"""
        mock_store = {}
        updater = BatchedStatusUpdater(
            buffer_size=100, flush_interval=10.0, underlying_store=mock_store
        )

        # 添加一些更新
        updater.queue_update("task-1", {"status": "pending"})
        updater.queue_update("task-2", {"status": "running"})

        assert updater.get_buffer_length() == 2
        assert len(mock_store) == 0

        # 关闭（应该自动刷新）
        updater.close()

        # 验证所有更新都已刷新
        assert updater.get_buffer_length() == 0
        assert len(mock_store) == 2
        assert "task-1" in mock_store
        assert "task-2" in mock_store


class TestBatchedStatusUpdaterConcurrency:
    """测试 BatchedStatusUpdater 的并发安全性"""

    def test_concurrent_batch_updates(self):
        """测试并发批量更新"""
        mock_store = {}
        updater = BatchedStatusUpdater(
            buffer_size=100, flush_interval=1.0, underlying_store=mock_store
        )

        num_threads = 10
        updates_per_thread = 50

        def batch_updates(thread_id: int):
            for i in range(updates_per_thread):
                task_id = f"task-{thread_id}-{i}"
                updater.queue_update(
                    task_id, {"status": "running", "thread": thread_id}
                )

        import threading

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=batch_updates, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # 手动刷新所有待处理的更新
        updater.flush()

        # 验证所有更新都成功
        expected_count = num_threads * updates_per_thread
        assert len(mock_store) == expected_count

        # 验证数据完整性
        for i in range(num_threads):
            for j in range(updates_per_thread):
                task_id = f"task-{i}-{j}"
                assert task_id in mock_store
                assert mock_store[task_id]["thread"] == i

    def test_concurrent_flush_and_query(self):
        """测试并发刷新和查询"""
        mock_store = {}
        updater = BatchedStatusUpdater(
            buffer_size=50, flush_interval=0.5, underlying_store=mock_store
        )

        import random
        import threading

        stop_flag = threading.Event()

        def update_producer():
            """持续添加更新的生产者"""
            count = 0
            while not stop_flag.is_set():
                updater.queue_update(f"task-{count}", {"status": "running"})
                count += 1
                time.sleep(0.001)  # 1ms

        def flush_consumer():
            """持续刷新的消费者"""
            while not stop_flag.is_set():
                time.sleep(0.1)  # 100ms
                updater.flush()

        # 启动线程
        producer = threading.Thread(target=update_producer)
        consumer = threading.Thread(target=flush_consumer)
        producer.start()
        consumer.start()

        # 运行 500ms
        time.sleep(0.5)
        stop_flag.set()

        producer.join()
        consumer.join()

        # 最终刷新
        updater.flush()

        # 验证数据完整性（无数据丢失）
        buffer_length = updater.get_buffer_length()
        assert buffer_length == 0, f"缓冲区应该为空，但有 {buffer_length} 个待处理更新"

    def test_concurrent_sync_and_batch_updates(self):
        """测试并发同步更新和批量更新"""
        mock_store = {}
        updater = BatchedStatusUpdater(
            buffer_size=100, flush_interval=1.0, underlying_store=mock_store
        )

        import threading

        num_sync_updates = 50
        num_batch_updates = 100

        def sync_updater():
            for i in range(num_sync_updates):
                updater.update_sync(f"sync-{i}", {"status": "completed"})

        def batch_updater():
            for i in range(num_batch_updates):
                updater.queue_update(f"batch-{i}", {"status": "pending"})
            updater.flush()

        t1 = threading.Thread(target=sync_updater)
        t2 = threading.Thread(target=batch_updater)

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        # 验证所有更新都成功
        assert len(mock_store) == num_sync_updates + num_batch_updates

        # 验证同步更新优先写入
        for i in range(num_sync_updates):
            assert f"sync-{i}" in mock_store
            assert mock_store[f"sync-{i}"]["status"] == "completed"

        # 验证批量更新也写入成功
        for i in range(num_batch_updates):
            assert f"batch-{i}" in mock_store
            assert mock_store[f"batch-{i}"]["status"] == "pending"
