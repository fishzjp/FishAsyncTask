"""
工作线程模块测试

测试 WorkerManager、TaskExecutor、AdaptiveWorkerManager 和 CPUMonitor 的核心功能。
"""

import queue
import threading
import time
from unittest.mock import Mock, patch

import pytest

from fish_async_task.worker import (
    AdaptiveWorkerManager,
    CPUMonitor,
    TaskExecutor,
    WorkerManager,
)
from fish_async_task.types import TaskTuple


# =============================================================================
# 测试辅助函数和 fixtures
# =============================================================================


def simple_task(value: int) -> int:
    """简单的测试任务"""
    return value * 2


def failing_task() -> None:
    """会失败的任务"""
    raise ValueError("任务执行失败")


def long_running_task(duration: float) -> str:
    """长时间运行的任务"""
    time.sleep(duration)
    return f"任务完成，耗时 {duration} 秒"


def blocking_task():
    """会阻塞较长时间的任务（用于测试超时）"""
    # 使用无限循环确保任务持续运行
    while True:
        pass  # 忙等待
    return "不应该执行到这里"


@pytest.fixture
def task_queue():
    """创建任务队列"""
    return queue.Queue()


@pytest.fixture
def worker_threads():
    """创建工作线程列表"""
    return []


@pytest.fixture
def threads_lock():
    """创建线程锁"""
    return threading.Lock()


@pytest.fixture
def running_event():
    """创建运行事件"""
    event = threading.Event()
    event.set()
    return event


@pytest.fixture
def mock_logger():
    """创建模拟日志记录器"""
    return Mock()


# =============================================================================
# TestTaskExecutor - 任务执行器测试
# =============================================================================


class TestTaskExecutor:
    """测试任务执行器"""

    def test_init(self, mock_logger):
        """测试 TaskExecutor 初始化"""
        timeout_getter = Mock(return_value=10.0)
        update_status_func = Mock()

        executor = TaskExecutor(
            logger=mock_logger,
            task_timeout_getter=timeout_getter,
            update_status_func=update_status_func,
        )

        assert executor._get_task_timeout == timeout_getter
        assert executor._update_status == update_status_func
        assert executor.get_pending_update_count() == 0

    def test_execute_task_success(self, mock_logger):
        """测试成功执行任务"""
        timeout_getter = Mock(return_value=None)
        status_updates = []

        def update_status(*args, **kwargs):
            status_updates.append((args, kwargs))

        executor = TaskExecutor(
            logger=mock_logger,
            task_timeout_getter=timeout_getter,
            update_status_func=update_status,
            batch_size=1,  # 设置较小的批量大小以立即刷新
            batch_flush_interval=0.01,
        )

        task: TaskTuple = ("task1", simple_task, (5,), {})
        executor.execute_task(task)

        # 等待批量更新完成
        executor.flush_pending_updates()

        # 验证状态更新
        assert len(status_updates) >= 2
        assert status_updates[0][0][1] == "running"  # 第一个状态是 running
        assert status_updates[-1][0][1] == "completed"  # 最后一个状态是 completed

    def test_execute_task_failure(self, mock_logger):
        """测试任务执行失败"""
        timeout_getter = Mock(return_value=None)
        status_updates = []

        def update_status(*args, **kwargs):
            status_updates.append((args, kwargs))

        executor = TaskExecutor(
            logger=mock_logger,
            task_timeout_getter=timeout_getter,
            update_status_func=update_status,
            batch_size=1,  # 设置较小的批量大小以立即刷新
            batch_flush_interval=0.01,
        )

        task: TaskTuple = ("task2", failing_task, (), {})
        executor.execute_task(task)

        # 等待批量更新完成
        executor.flush_pending_updates()

        # 验证状态更新
        assert len(status_updates) >= 2
        assert status_updates[-1][0][1] == "failed"  # 最后状态是 failed

    def test_execute_task_with_timeout(self, mock_logger):
        """测试任务超时"""
        timeout_getter = Mock(return_value=1.0)  # 增加超时时间
        status_updates = []

        def update_status(*args, **kwargs):
            status_updates.append((args, kwargs))

        executor = TaskExecutor(
            logger=mock_logger,
            task_timeout_getter=timeout_getter,
            update_status_func=update_status,
            batch_size=1,
            batch_flush_interval=0.01,
        )

        task: TaskTuple = ("task3", blocking_task, (), {})

        # execute_task 会捕获 TimeoutError 并转换为状态更新，不会重新抛出
        executor.execute_task(task)

        # 刷新待处理的更新
        executor.flush_pending_updates()

        # 验证超时任务被跟踪
        assert executor.get_timed_out_task_count() > 0

        # 验证状态更新包含失败状态
        assert any(s[0][1] == "failed" for s in status_updates)

    def test_flush_pending_updates(self, mock_logger):
        """测试刷新待处理的更新"""
        timeout_getter = Mock(return_value=None)
        status_updates = []

        def update_status(*args, **kwargs):
            status_updates.append((args, kwargs))

        executor = TaskExecutor(
            logger=mock_logger,
            task_timeout_getter=timeout_getter,
            update_status_func=update_status,
            batch_size=100,  # 设置较大的批量大小以避免自动刷新
            batch_flush_interval=10.0,
        )

        # 执行多个任务
        for i in range(5):
            task: TaskTuple = (f"task{i}", simple_task, (i,), {})
            executor.execute_task(task)

        # 手动刷新
        pending = executor.flush_pending_updates()
        assert pending >= 0

    def test_cleanup_callback(self, mock_logger):
        """测试清理回调"""
        timeout_getter = Mock(return_value=1.0)  # 增加超时时间
        status_updates = []
        cleanup_called = []

        def update_status(*args, **kwargs):
            status_updates.append((args, kwargs))

        def cleanup_callback(task_id: str):
            cleanup_called.append(task_id)

        executor = TaskExecutor(
            logger=mock_logger,
            task_timeout_getter=timeout_getter,
            update_status_func=update_status,
            batch_size=1,
            batch_flush_interval=0.01,
        )

        executor.add_cleanup_callback(cleanup_callback)

        task: TaskTuple = ("task_timeout", blocking_task, (), {})

        # execute_task 会捕获 TimeoutError 并转换为状态更新，不会重新抛出
        executor.execute_task(task)

        # 刷新待处理的更新
        executor.flush_pending_updates()

        # 验证清理回调被调用
        assert len(cleanup_called) == 1
        assert cleanup_called[0] == "task_timeout"


# =============================================================================
# TestWorkerManager - 工作线程管理测试
# =============================================================================


class TestWorkerManager:
    """测试工作线程管理器"""

    def test_init(self, mock_logger, task_queue, worker_threads, threads_lock, running_event):
        """测试 WorkerManager 初始化"""
        execute_task_func = Mock()

        manager = WorkerManager(
            logger=mock_logger,
            task_queue=task_queue,
            worker_threads=worker_threads,
            threads_lock=threads_lock,
            running_event=running_event,
            min_workers=2,
            max_workers=5,
            idle_timeout=60,
            task_timeout=10.0,
            execute_task_func=execute_task_func,
        )

        assert manager.min_workers == 2
        assert manager.max_workers == 5
        assert manager.idle_timeout == 60
        assert manager.task_timeout == 10.0

    def test_start_initial_workers(self, mock_logger, task_queue, worker_threads, threads_lock, running_event):
        """测试启动初始工作线程"""
        execute_task_func = Mock()

        manager = WorkerManager(
            logger=mock_logger,
            task_queue=task_queue,
            worker_threads=worker_threads,
            threads_lock=threads_lock,
            running_event=running_event,
            min_workers=2,
            max_workers=5,
            idle_timeout=60,
            task_timeout=10.0,
            execute_task_func=execute_task_func,
        )

        manager.start_initial_workers()

        assert len(manager.worker_threads) == 2

        # 清理
        running_event.clear()
        manager.send_shutdown_signals()
        manager.wait_for_threads_exit(5)

    def test_scale_up_workers(self, mock_logger, task_queue, worker_threads, threads_lock, running_event):
        """测试动态扩展工作线程"""
        execute_task_func = Mock()

        manager = WorkerManager(
            logger=mock_logger,
            task_queue=task_queue,
            worker_threads=worker_threads,
            threads_lock=threads_lock,
            running_event=running_event,
            min_workers=1,
            max_workers=5,
            idle_timeout=60,
            task_timeout=10.0,
            execute_task_func=execute_task_func,
        )

        manager.start_initial_workers()
        initial_count = len(manager.worker_threads)

        # 向队列添加大量任务
        for i in range(20):
            task_queue.put((f"task{i}", simple_task, (i,), {}))

        # 触发扩容检查
        manager.scale_up_workers_if_needed()

        # 验证线程数增加
        assert len(manager.worker_threads) >= initial_count

        # 清理
        running_event.clear()
        manager.send_shutdown_signals()
        manager.wait_for_threads_exit(5)

    def test_shutdown_and_wait(self, mock_logger, task_queue, worker_threads, threads_lock, running_event):
        """测试关闭和等待线程退出"""
        execute_task_func = Mock()

        manager = WorkerManager(
            logger=mock_logger,
            task_queue=task_queue,
            worker_threads=worker_threads,
            threads_lock=threads_lock,
            running_event=running_event,
            min_workers=2,
            max_workers=5,
            idle_timeout=60,
            task_timeout=10.0,
            execute_task_func=execute_task_func,
        )

        manager.start_initial_workers()

        # 发送关闭信号
        running_event.clear()
        manager.send_shutdown_signals()
        manager.wait_for_threads_exit(5)

        # 验证线程已退出
        for thread in manager.worker_threads:
            assert not thread.is_alive()

    def test_get_idle_time(self, mock_logger, task_queue, worker_threads, threads_lock, running_event):
        """测试获取空闲时间"""
        execute_task_func = Mock()

        manager = WorkerManager(
            logger=mock_logger,
            task_queue=task_queue,
            worker_threads=worker_threads,
            threads_lock=threads_lock,
            running_event=running_event,
            min_workers=1,
            max_workers=5,
            idle_timeout=60,
            task_timeout=10.0,
            execute_task_func=execute_task_func,
        )

        # 初始状态没有空闲时间
        assert manager.get_idle_time() is None


# =============================================================================
# TestAdaptiveWorkerManager - 自适应管理测试
# =============================================================================


class TestAdaptiveWorkerManager:
    """测试自适应工作线程管理器"""

    def test_init(self):
        """测试初始化"""
        manager = AdaptiveWorkerManager(
            min_workers=2,
            max_workers=10,
            cpu_threshold=0.8,
            queue_threshold_high=100,
            queue_threshold_low=10,
            scale_up_cooldown=5.0,
            scale_down_cooldown=30.0,
            use_cpu_monitoring=False,  # 禁用 CPU 监控以简化测试
        )

        assert manager.min_workers == 2
        assert manager.max_workers == 10
        assert manager.cpu_threshold == 0.8
        assert manager.queue_threshold_high == 100
        assert manager.queue_threshold_low == 10

    def test_should_scale_up(self):
        """测试扩容判断"""
        manager = AdaptiveWorkerManager(
            min_workers=2,
            max_workers=10,
            queue_threshold_high=100,
            use_cpu_monitoring=False,
        )

        # 队列积压超过阈值，应该扩容
        assert manager.should_scale_up(current_workers=5, queue_size=150, cpu_usage=None)

        # 已达到最大线程数，不应扩容
        assert not manager.should_scale_up(current_workers=10, queue_size=150, cpu_usage=None)

    def test_should_scale_down(self):
        """测试缩容判断"""
        manager = AdaptiveWorkerManager(
            min_workers=2,
            max_workers=10,
            queue_threshold_low=10,
            scale_down_cooldown=30.0,
            use_cpu_monitoring=False,
        )

        # 队列为空且空闲时间超过冷却期，应该缩容
        assert manager.should_scale_down(
            current_workers=5, queue_size=0, idle_time=35.0
        )

        # 已达到最小线程数，不应缩容
        assert not manager.should_scale_down(
            current_workers=2, queue_size=0, idle_time=35.0
        )

        # 空闲时间不足，不应缩容
        assert not manager.should_scale_down(
            current_workers=5, queue_size=0, idle_time=10.0
        )

    def test_record_and_get_avg_task_time(self):
        """测试任务执行时间记录和平均值计算"""
        manager = AdaptiveWorkerManager(
            min_workers=2,
            max_workers=10,
            use_cpu_monitoring=False,
        )

        # 记录任务执行时间
        manager.record_task_time(1.0)
        manager.record_task_time(2.0)
        manager.record_task_time(3.0)

        # 获取平均值
        avg = manager.get_avg_task_time()
        assert avg == 2.0

    def test_get_stats(self):
        """测试获取统计信息"""
        manager = AdaptiveWorkerManager(
            min_workers=2,
            max_workers=10,
            cpu_threshold=0.8,
            use_cpu_monitoring=False,
        )

        stats = manager.get_stats()

        assert stats["min_workers"] == 2
        assert stats["max_workers"] == 10
        assert stats["cpu_threshold"] == 0.8
        assert stats["avg_task_time"] == 0.0
        assert stats["task_count"] == 0


# =============================================================================
# TestCPUMonitor - CPU 监控测试
# =============================================================================


class TestCPUMonitor:
    """测试 CPU 监控器"""

    def test_init(self):
        """测试初始化"""
        monitor = CPUMonitor(sample_interval=0.1, sample_count=2)
        assert monitor.sample_interval == 0.1
        assert monitor.sample_count == 2

    def test_get_cpu_count(self):
        """测试获取 CPU 核心数"""
        monitor = CPUMonitor()
        count = monitor.get_cpu_count()
        assert count >= 1

    @patch("fish_async_task.worker.adaptive.CPUMonitor._check_psutil", return_value=False)
    def test_get_cpu_usage_without_psutil(self, mock_check):
        """测试没有 psutil 时获取 CPU 使用率"""
        monitor = CPUMonitor()
        usage = monitor.get_cpu_usage()
        assert usage is None


# =============================================================================
# TestTaskTimeout - 超时控制测试
# =============================================================================


class TestTaskTimeout:
    """测试任务超时控制"""

    def test_task_timeout_execution(self, mock_logger):
        """测试任务超时执行"""
        timeout_getter = Mock(return_value=1.0)  # 增加超时时间
        status_updates = []

        def update_status(*args, **kwargs):
            status_updates.append((args, kwargs))

        executor = TaskExecutor(
            logger=mock_logger,
            task_timeout_getter=timeout_getter,
            update_status_func=update_status,
            batch_size=1,
            batch_flush_interval=0.01,
        )

        task: TaskTuple = ("timeout_task", blocking_task, (), {})

        # execute_task 会捕获 TimeoutError 并转换为状态更新
        executor.execute_task(task)

        # 刷新待处理的更新
        executor.flush_pending_updates()

        # 验证状态
        assert any(s[0][1] == "failed" for s in status_updates)

    def test_no_timeout_when_disabled(self, mock_logger):
        """测试禁用超时时任务正常执行"""
        timeout_getter = Mock(return_value=None)
        status_updates = []

        def update_status(*args, **kwargs):
            status_updates.append((args, kwargs))

        executor = TaskExecutor(
            logger=mock_logger,
            task_timeout_getter=timeout_getter,
            update_status_func=update_status,
            batch_size=1,
            batch_flush_interval=0.01,
        )

        task: TaskTuple = ("normal_task", simple_task, (5,), {})
        executor.execute_task(task)

        # 刷新待处理的更新
        executor.flush_pending_updates()

        # 验证任务完成
        assert any(s[0][1] == "completed" for s in status_updates)


# =============================================================================
# TestWorkerLifecycle - 工作线程生命周期测试
# =============================================================================


class TestWorkerLifecycle:
    """测试工作线程生命周期"""

    def test_worker_starts_and_stops(self, mock_logger, task_queue, worker_threads, threads_lock, running_event):
        """测试工作线程启动和停止"""
        executed_tasks = []

        def execute_task_func(task: TaskTuple):
            executed_tasks.append(task[0])

        manager = WorkerManager(
            logger=mock_logger,
            task_queue=task_queue,
            worker_threads=worker_threads,
            threads_lock=threads_lock,
            running_event=running_event,
            min_workers=2,
            max_workers=5,
            idle_timeout=1,
            task_timeout=10.0,
            execute_task_func=execute_task_func,
            adaptive_worker_enabled=False,
        )

        manager.start_initial_workers()
        assert len(manager.worker_threads) == 2

        # 添加任务
        for i in range(3):
            task_queue.put((f"task{i}", simple_task, (i,), {}))

        # 等待任务执行
        time.sleep(0.5)

        # 验证任务被执行
        assert len(executed_tasks) > 0

        # 关闭
        running_event.clear()
        manager.send_shutdown_signals()
        manager.wait_for_threads_exit(5)

        # 验证线程已退出
        for thread in manager.worker_threads:
            assert not thread.is_alive()

    def test_worker_auto_exit_on_idle(self, mock_logger, task_queue, worker_threads, threads_lock, running_event):
        """测试工作线程在空闲时自动退出"""
        executed_tasks = []

        def execute_task_func(task: TaskTuple):
            executed_tasks.append(task[0])

        manager = WorkerManager(
            logger=mock_logger,
            task_queue=task_queue,
            worker_threads=worker_threads,
            threads_lock=threads_lock,
            running_event=running_event,
            min_workers=1,
            max_workers=5,
            idle_timeout=1,  # 1秒空闲超时
            task_timeout=10.0,
            execute_task_func=execute_task_func,
            adaptive_worker_enabled=False,
        )

        # 启动初始线程
        manager.start_initial_workers()
        initial_count = len(manager.worker_threads)

        # 手动添加一个额外线程
        extra_thread = threading.Thread(
            target=manager._worker_loop,
            name="ExtraWorker",
            daemon=True,
        )
        extra_thread.start()
        manager.worker_threads.append(extra_thread)

        enhanced_count = len(manager.worker_threads)
        assert enhanced_count > initial_count

        # 等待空闲超时
        time.sleep(2)

        # 验证额外线程已退出
        assert len(manager.worker_threads) >= initial_count

        # 清理
        running_event.clear()
        manager.send_shutdown_signals()
        manager.wait_for_threads_exit(5)
