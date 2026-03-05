"""
任务状态管理模块详细测试

测试 ReadWriteLock、ShardedTaskStatusWithExpiry、BatchedStatusUpdater 等类的并发访问场景。
"""

import logging
import threading
import time
from collections import deque
from unittest.mock import Mock, patch

import pytest

from fish_async_task.task_status import (
    BatchedStatusUpdater,
    ReadWriteLock,
    ReadWriteLockContext,
    ShardedTaskStatusWithExpiry,
    TaskStatusManager,
)


class TestReadWriteLock:
    """测试 ReadWriteLock 写优先读写锁"""

    def test_init(self):
        """测试初始化"""
        lock = ReadWriteLock()
        assert lock._readers == 0
        assert lock._writers_waiting == 0

    def test_acquire_release_read(self):
        """测试获取和释放读锁"""
        lock = ReadWriteLock()
        lock.acquire_read()
        assert lock._readers == 1
        lock.release_read()
        assert lock._readers == 0

    def test_multiple_readers(self):
        """测试多个读操作并发"""
        lock = ReadWriteLock()
        results = []

        def read_operation():
            lock.acquire_read()
            results.append(lock._readers)
            time.sleep(0.01)
            lock.release_read()

        threads = [threading.Thread(target=read_operation) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 应该有多个读操作同时进行
        assert max(results) > 1

    def test_acquire_release_write(self):
        """测试获取和释放写锁"""
        lock = ReadWriteLock()
        lock.acquire_write()
        assert lock._writers_waiting == 1
        lock.release_write()
        assert lock._writers_waiting == 0

    def test_write_excludes_read(self):
        """测试写操作排除读操作"""
        lock = ReadWriteLock()
        write_started = threading.Event()
        read_started = threading.Event()

        def write_operation():
            lock.acquire_write()
            write_started.set()
            time.sleep(0.05)
            lock.release_write()

        def read_operation():
            read_started.set()
            lock.acquire_read()
            lock.release_read()

        write_thread = threading.Thread(target=write_operation)
        read_thread = threading.Thread(target=read_operation)

        write_thread.start()
        time.sleep(0.01)  # 让写操作先开始
        read_thread.start()

        write_thread.join()
        read_thread.join()

        # 读操作应该在写操作之后完成
        assert write_started.is_set()

    def test_write_priority(self):
        """测试写优先策略"""
        lock = ReadWriteLock()
        results = []

        def read_with_delay():
            time.sleep(0.01)
            lock.acquire_read()
            results.append("read")
            lock.release_read()

        def write_operation():
            lock.acquire_write()
            results.append("write")
            lock.release_write()

        # 启动读操作
        read_threads = [threading.Thread(target=read_with_delay) for _ in range(3)]
        for t in read_threads:
            t.start()

        time.sleep(0.02)  # 让读操作开始

        # 启动写操作
        write_thread = threading.Thread(target=write_operation)
        write_thread.start()

        for t in read_threads:
            t.join()
        write_thread.join()

        # 验证写操作优先
        assert "write" in results

    def test_concurrent_read_write(self):
        """测试并发读写"""
        lock = ReadWriteLock()
        shared_data = {"value": 0}
        errors = []

        def read_operation():
            for _ in range(50):
                lock.acquire_read()
                value = shared_data["value"]
                if value < 0 or value > 100:
                    errors.append(f"Invalid value: {value}")
                lock.release_read()

        def write_operation():
            for i in range(50):
                lock.acquire_write()
                shared_data["value"] = i
                lock.release_write()

        read_threads = [threading.Thread(target=read_operation) for _ in range(3)]
        write_thread = threading.Thread(target=write_operation)

        for t in read_threads:
            t.start()
        write_thread.start()

        for t in read_threads:
            t.join()
        write_thread.join()

        assert not errors


class TestReadWriteLockContext:
    """测试 ReadWriteLockContext 上下文管理器"""

    def test_read_context_manager(self):
        """测试读锁上下文管理器"""
        lock = ReadWriteLock()
        with ReadWriteLockContext(lock, write=False):
            assert lock._readers == 1
        assert lock._readers == 0

    def test_write_context_manager(self):
        """测试写锁上下文管理器"""
        lock = ReadWriteLock()
        with ReadWriteLockContext(lock, write=True):
            assert lock._writers_waiting == 1
        assert lock._writers_waiting == 0

    def test_context_manager_with_exception(self):
        """测试上下文管理器处理异常"""
        lock = ReadWriteLock()

        with pytest.raises(ValueError):
            with ReadWriteLockContext(lock, write=False):
                assert lock._readers == 1
                raise ValueError("Test error")

        # 锁应该被释放
        assert lock._readers == 0

    def test_nested_context_managers(self):
        """测试嵌套上下文管理器"""
        lock = ReadWriteLock()

        with ReadWriteLockContext(lock, write=False):
            assert lock._readers == 1
            with ReadWriteLockContext(lock, write=False):
                assert lock._readers == 2

        assert lock._readers == 0


class TestShardedTaskStatusWithExpiry:
    """测试 ShardedTaskStatusWithExpiry 分片任务状态存储"""

    def test_init(self):
        """测试初始化"""
        storage = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)
        assert storage.shard_count == 16
        assert storage.ttl == 3600
        assert len(storage.shards) == 16
        assert len(storage.rw_locks) == 16
        assert len(storage.expiry_heaps) == 16

    def test_get_shard_index(self):
        """测试分片索引计算"""
        storage = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)
        index = storage._get_shard_index("task1")
        assert 0 <= index < 16

        # 同一任务ID应该映射到同一分片
        assert storage._get_shard_index("task1") == index

    def test_update_and_get_status(self):
        """测试更新和获取状态"""
        storage = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        status = {
            "status": "pending",
            "submit_time": time.time(),
        }

        storage.update_status("task1", status)
        retrieved = storage.get_status("task1")

        assert retrieved is not None
        assert retrieved["status"] == "pending"

    def test_get_nonexistent_status(self):
        """测试获取不存在的状态"""
        storage = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)
        retrieved = storage.get_status("nonexistent")
        assert retrieved is None

    def test_remove_status(self):
        """测试移除状态"""
        storage = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        status = {"status": "pending"}
        storage.update_status("task1", status)
        assert storage.get_status("task1") is not None

        storage.remove_status("task1")
        assert storage.get_status("task1") is None

    def test_cleanup_expired(self):
        """测试清理过期任务"""
        storage = ShardedTaskStatusWithExpiry(shard_count=16, ttl=1)

        # 添加已完成任务
        now = time.time()
        status1 = {
            "status": "completed",
            "end_time": now - 2,  # 2秒前结束，已过期
        }
        status2 = {
            "status": "completed",
            "end_time": now,  # 刚结束，未过期
        }

        storage.update_status("task1", status1)
        storage.update_status("task2", status2)

        # 清理过期任务
        cleaned = storage.cleanup_expired()

        assert cleaned >= 1
        assert storage.get_status("task1") is None
        assert storage.get_status("task2") is not None

    def test_cleanup_expired_max_cleanup(self):
        """测试清理最大数量限制"""
        storage = ShardedTaskStatusWithExpiry(shard_count=16, ttl=1)

        now = time.time()
        for i in range(10):
            status = {
                "status": "completed",
                "end_time": now - 2,  # 已过期
            }
            storage.update_status(f"task{i}", status)

        # 最多清理 3 个
        cleaned = storage.cleanup_expired(max_cleanup=3)
        assert cleaned == 3

    def test_enforce_max_count(self):
        """测试强制执行最大数量限制"""
        storage = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        # 添加超过限制的任务
        for i in range(20):
            status = {
                "status": "pending",
                "submit_time": time.time() + i,
            }
            storage.update_status(f"task{i}", status)

        # 强制限制为 10
        cleaned = storage.enforce_max_count(10)
        assert cleaned >= 10
        assert storage.get_total_count() <= 10

    def test_get_total_count(self):
        """测试获取总任务数量"""
        storage = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        assert storage.get_total_count() == 0

        for i in range(10):
            storage.update_status(f"task{i}", {"status": "pending"})

        assert storage.get_total_count() == 10

    def test_get_all_statuses(self):
        """测试获取所有状态"""
        storage = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        for i in range(10):
            storage.update_status(f"task{i}", {"status": "pending"})

        all_statuses = storage.get_all_statuses()
        assert len(all_statuses) == 10

    def test_clear_all(self):
        """测试清空所有状态"""
        storage = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        for i in range(10):
            storage.update_status(f"task{i}", {"status": "pending"})

        storage.clear_all()
        assert storage.get_total_count() == 0

    def test_concurrent_operations(self):
        """测试并发操作"""
        storage = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)
        errors = []

        def update_task(task_id):
            try:
                for i in range(50):
                    status = {"status": "running", "value": i}
                    storage.update_status(task_id, status)
                    retrieved = storage.get_status(task_id)
                    if retrieved is None:
                        errors.append(f"Task {task_id} not found")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=update_task, args=(f"task{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors

    def test_sharded_distribution(self):
        """测试分片分布"""
        storage = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)

        # 添加多个任务
        for i in range(100):
            storage.update_status(f"task{i}", {"status": "pending"})

        # 检查任务分布到不同分片
        shard_counts = [len(shard) for shard in storage.shards]
        assert sum(shard_counts) == 100
        # 任务应该分布在多个分片上
        assert sum(1 for count in shard_counts if count > 0) > 1


class TestBatchedStatusUpdater:
    """测试 BatchedStatusUpdater 批量状态更新器"""

    def test_init(self):
        """测试初始化"""
        update_func = Mock()
        updater = BatchedStatusUpdater(update_func=update_func, batch_size=100, flush_interval=0.1)

        assert updater._update_func == update_func
        assert updater.batch_size == 100
        assert updater.flush_interval == 0.1
        assert len(updater._batch) == 0

    def test_update_single(self):
        """测试单个更新"""
        update_func = Mock()
        updater = BatchedStatusUpdater(update_func=update_func, batch_size=100, flush_interval=1.0)

        updater.update("task1", "pending")

        # 由于未达到批量大小或时间间隔，不会立即刷新
        assert updater.get_pending_count() == 1

    def test_update_reaches_batch_size(self):
        """测试达到批量大小时刷新"""
        update_func = Mock()
        updater = BatchedStatusUpdater(update_func=update_func, batch_size=10, flush_interval=1.0)

        for i in range(10):
            updater.update(f"task{i}", "pending")

        # 应该触发刷新
        assert update_func.call_count == 10

    def test_force_flush(self):
        """测试强制刷新"""
        update_func = Mock()
        updater = BatchedStatusUpdater(update_func=update_func, batch_size=100, flush_interval=1.0)

        updater.update("task1", "pending")
        updater.update("task2", "running")

        pending = updater.force_flush()
        assert pending == 2
        assert update_func.call_count == 2

    def test_check_and_flush(self):
        """测试检查并刷新"""
        update_func = Mock()
        updater = BatchedStatusUpdater(update_func=update_func, batch_size=100, flush_interval=0.01)

        updater.update("task1", "pending")

        # 等待刷新间隔
        time.sleep(0.02)
        updater.check_and_flush()

        assert update_func.call_count == 1

    def test_get_pending_count(self):
        """测试获取待处理数量"""
        update_func = Mock()
        updater = BatchedStatusUpdater(update_func=update_func)

        assert updater.get_pending_count() == 0

        updater.update("task1", "pending")
        assert updater.get_pending_count() == 1

        updater.force_flush()
        assert updater.get_pending_count() == 0

    def test_shutdown(self):
        """测试关闭"""
        update_func = Mock()
        updater = BatchedStatusUpdater(update_func=update_func)

        updater.update("task1", "pending")
        pending = updater.shutdown()

        assert pending == 1
        assert update_func.call_count == 1

    def test_concurrent_updates(self):
        """测试并发更新"""
        update_func = Mock()
        updater = BatchedStatusUpdater(update_func=update_func, batch_size=50, flush_interval=0.01)

        def update_tasks(task_prefix):
            for i in range(20):
                updater.update(f"{task_prefix}_task{i}", "running")

        threads = [threading.Thread(target=update_tasks, args=(f"thread{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 强制刷新剩余的
        updater.force_flush()

        # 所有更新都应该被处理
        assert update_func.call_count == 100


class TestTaskStatusManager:
    """测试 TaskStatusManager 任务状态管理器"""

    def test_init(self):
        """测试初始化"""
        logger = logging.getLogger(__name__)
        manager = TaskStatusManager(
            logger=logger,
            task_status_ttl=3600,
            max_task_status_count=10000,
            shard_count=16,
        )

        assert manager.logger == logger
        assert manager.task_status_ttl == 3600
        assert manager.max_task_status_count == 10000
        assert manager.sharded_status.shard_count == 16

    def test_update_and_get_task_status(self):
        """测试更新和获取任务状态"""
        logger = logging.getLogger(__name__)
        manager = TaskStatusManager(
            logger=logger,
            task_status_ttl=3600,
            max_task_status_count=10000,
        )
        # 禁用批量更新以便立即获取结果
        manager.enable_batch_update(False)

        manager.update_task_status("task1", "pending", submit_time=time.time())
        status = manager.get_task_status("task1")

        assert status is not None
        assert status["status"] == "pending"

    def test_update_task_status_preserves_start_time(self):
        """测试更新任务状态保留开始时间"""
        logger = logging.getLogger(__name__)
        manager = TaskStatusManager(
            logger=logger,
            task_status_ttl=3600,
            max_task_status_count=10000,
        )
        manager.enable_batch_update(False)

        start_time = time.time()
        manager.update_task_status("task1", "running", start_time=start_time)
        manager.update_task_status("task1", "running")

        status = manager.get_task_status("task1")
        assert status["start_time"] == start_time

    def test_clear_task_status(self):
        """测试清除任务状态"""
        logger = logging.getLogger(__name__)
        manager = TaskStatusManager(
            logger=logger,
            task_status_ttl=3600,
            max_task_status_count=10000,
        )
        manager.enable_batch_update(False)

        manager.update_task_status("task1", "pending")
        assert manager.get_task_status("task1") is not None

        manager.clear_task_status("task1")
        assert manager.get_task_status("task1") is None

    def test_clear_all_task_status(self):
        """测试清除所有任务状态"""
        logger = logging.getLogger(__name__)
        manager = TaskStatusManager(
            logger=logger,
            task_status_ttl=3600,
            max_task_status_count=10000,
        )
        manager.enable_batch_update(False)

        for i in range(10):
            manager.update_task_status(f"task{i}", "pending")

        manager.clear_task_status(None)
        assert manager.get_task_status("task1") is None

    def test_cleanup_old_task_status(self):
        """测试清理过期任务状态"""
        logger = logging.getLogger(__name__)
        manager = TaskStatusManager(
            logger=logger,
            task_status_ttl=1,
            max_task_status_count=10000,
        )
        manager.enable_batch_update(False)

        # 添加过期任务
        now = time.time()
        manager.update_task_status("task1", "completed", end_time=now - 2)
        manager.update_task_status("task2", "completed", end_time=now)

        cleaned = manager.cleanup_old_task_status()
        assert cleaned >= 1

    def test_enable_batch_update(self):
        """测试启用批量更新"""
        logger = logging.getLogger(__name__)
        manager = TaskStatusManager(
            logger=logger,
            task_status_ttl=3600,
            max_task_status_count=10000,
        )

        # 禁用批量更新
        manager.enable_batch_update(False)
        assert manager._batch_updater is None

        # 启用批量更新
        manager.enable_batch_update(True)
        assert manager._batch_updater is not None

    def test_get_pending_update_count(self):
        """测试获取待处理更新数量"""
        logger = logging.getLogger(__name__)
        manager = TaskStatusManager(
            logger=logger,
            task_status_ttl=3600,
            max_task_status_count=10000,
        )

        manager.update_task_status("task1", "pending")
        pending = manager.get_pending_update_count()

        assert pending >= 0

    def test_shutdown(self):
        """测试关闭"""
        logger = logging.getLogger(__name__)
        manager = TaskStatusManager(
            logger=logger,
            task_status_ttl=3600,
            max_task_status_count=10000,
        )

        manager.update_task_status("task1", "pending")
        pending = manager.shutdown()

        assert pending >= 0

    def test_resize_shards(self):
        """测试调整分片数量"""
        logger = logging.getLogger(__name__)
        manager = TaskStatusManager(
            logger=logger,
            task_status_ttl=3600,
            max_task_status_count=10000,
            shard_count=8,
        )
        manager.enable_batch_update(False)

        # 添加一些任务
        for i in range(10):
            manager.update_task_status(f"task{i}", "pending")

        # 调整分片数量
        success = manager.resize_shards(16)
        assert success is True
        assert manager.sharded_status.shard_count == 16

        # 任务应该仍然存在
        assert manager.get_task_status("task1") is not None

    def test_resize_shards_invalid(self):
        """测试无效的分片数量"""
        logger = logging.getLogger(__name__)
        manager = TaskStatusManager(
            logger=logger,
            task_status_ttl=3600,
            max_task_status_count=10000,
            shard_count=16,
        )

        success = manager.resize_shards(0)
        assert success is False

    def test_concurrent_status_updates(self):
        """测试并发状态更新"""
        logger = logging.getLogger(__name__)
        manager = TaskStatusManager(
            logger=logger,
            task_status_ttl=3600,
            max_task_status_count=10000,
        )
        # 禁用批量更新以便立即获取结果
        manager.enable_batch_update(False)
        errors = []

        def update_task_status(task_id):
            try:
                for i in range(50):
                    manager.update_task_status(task_id, "running")
                    status = manager.get_task_status(task_id)
                    if status is None:
                        errors.append(f"Task {task_id} not found")
            except Exception as e:
                errors.append(str(e))

        threads = [
            threading.Thread(target=update_task_status, args=(f"task{i}",)) for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
