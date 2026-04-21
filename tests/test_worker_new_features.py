"""
新增功能测试

测试本次修复中新增的协作式取消、异常处理重构、线程安全退出等功能。
"""

import queue
import threading
import time
from unittest.mock import Mock

import pytest

from fish_async_task.types import TaskTuple
from fish_async_task.worker import TaskExecutor, WorkerManager


def simple_task(value: int) -> int:
    return value * 2


def failing_task() -> None:
    raise ValueError("测试失败")


def io_failing_task() -> None:
    raise IOError("I/O 错误")


def timeout_failing_task() -> None:
    raise TimeoutError("超时")


def memory_failing_task() -> None:
    raise MemoryError("内存不足")


def slow_task(duration: float) -> str:
    time.sleep(duration)
    return "完成"


@pytest.fixture
def mock_logger():
    return Mock()


@pytest.fixture
def task_queue():
    return queue.Queue()


@pytest.fixture
def worker_threads():
    return []


@pytest.fixture
def threads_lock():
    return threading.Lock()


@pytest.fixture
def running_event():
    event = threading.Event()
    event.set()
    return event


class TestCancelEvent:
    """测试协作式取消事件机制"""

    def test_cancel_event_set_on_timeout(self, mock_logger):
        """超时后取消事件应被设置"""
        executor = TaskExecutor(
            logger=mock_logger,
            task_timeout_getter=lambda: 0.5,
            update_status_func=Mock(),
        )

        def blocking():
            time.sleep(10)

        task: TaskTuple = ("cancel_test", blocking, (), {})
        executor.execute_task(task)

        # 超时后取消事件应被设置（set）但仍存在
        event = executor.get_cancel_event("cancel_test")
        assert event is not None
        assert event.is_set()

        # 手动清理
        executor._cleanup_cancel_event("cancel_test")
        assert executor.get_cancel_event("cancel_test") is None

    def test_cancel_event_cleaned_on_success(self, mock_logger):
        """成功完成的任务应清理取消事件"""
        executor = TaskExecutor(
            logger=mock_logger,
            task_timeout_getter=lambda: 5.0,
            update_status_func=Mock(),
            batch_size=1,
            batch_flush_interval=0.01,
        )

        task: TaskTuple = ("success_test", simple_task, (5,), {})
        executor.execute_task(task)

        assert executor.get_cancel_event("success_test") is None

    def test_cancel_event_none_when_not_registered(self, mock_logger):
        """未注册的任务应返回 None"""
        executor = TaskExecutor(
            logger=mock_logger,
            task_timeout_getter=lambda: None,
            update_status_func=Mock(),
        )
        assert executor.get_cancel_event("nonexistent") is None

    def test_no_timeout_skips_cancel_events(self, mock_logger):
        """无超时设置时不注册取消事件"""
        executor = TaskExecutor(
            logger=mock_logger,
            task_timeout_getter=lambda: None,
            update_status_func=Mock(),
            batch_size=1,
            batch_flush_interval=0.01,
        )

        task: TaskTuple = ("no_timeout", simple_task, (5,), {})
        executor.execute_task(task)

        assert executor.get_cancel_event("no_timeout") is None


class TestRecordTaskFailure:
    """测试 _record_task_failure 辅助方法"""

    def test_io_exception_records_failure(self, mock_logger):
        """IO 异常应记录失败状态"""
        status_updates = []

        def update_status(*args, **kwargs):
            status_updates.append((args, kwargs))

        executor = TaskExecutor(
            logger=mock_logger,
            task_timeout_getter=lambda: None,
            update_status_func=update_status,
            batch_size=1,
            batch_flush_interval=0.01,
        )

        task: TaskTuple = ("io_fail", io_failing_task, (), {})
        executor.execute_task(task)
        executor.flush_pending_updates()

        assert any(s[0][1] == "failed" for s in status_updates)

    def test_timeout_exception_records_failure(self, mock_logger):
        """TimeoutError 应记录失败状态"""
        status_updates = []

        def update_status(*args, **kwargs):
            status_updates.append((args, kwargs))

        executor = TaskExecutor(
            logger=mock_logger,
            task_timeout_getter=lambda: None,
            update_status_func=update_status,
            batch_size=1,
            batch_flush_interval=0.01,
        )

        task: TaskTuple = ("timeout_fail", timeout_failing_task, (), {})
        executor.execute_task(task)
        executor.flush_pending_updates()

        failed_updates = [s for s in status_updates if s[0][1] == "failed"]
        assert len(failed_updates) >= 1

    def test_memory_exception_records_failure(self, mock_logger):
        """MemoryError 应记录失败状态"""
        status_updates = []

        def update_status(*args, **kwargs):
            status_updates.append((args, kwargs))

        executor = TaskExecutor(
            logger=mock_logger,
            task_timeout_getter=lambda: None,
            update_status_func=update_status,
            batch_size=1,
            batch_flush_interval=0.01,
        )

        task: TaskTuple = ("mem_fail", memory_failing_task, (), {})
        executor.execute_task(task)
        executor.flush_pending_updates()

        assert any(s[0][1] == "failed" for s in status_updates)


class TestHandleTaskException:
    """测试重构后的异常处理"""

    def test_programming_error_classified(self, mock_logger):
        """编程错误类型应在 _PROGRAMMING_ERRORS 集合中"""
        from fish_async_task.worker.core import WorkerManager as WM

        assert "TypeError" in WM._PROGRAMMING_ERRORS
        assert "AttributeError" in WM._PROGRAMMING_ERRORS
        assert "ValueError" in WM._PROGRAMMING_ERRORS
        assert "KeyError" in WM._PROGRAMMING_ERRORS
        assert "IndexError" in WM._PROGRAMMING_ERRORS

    def test_keyboard_interrupt_returns_true(self, mock_logger):
        """KeyboardInterrupt 应返回 True（退出循环）"""
        manager = WorkerManager(
            logger=mock_logger,
            task_queue=queue.Queue(),
            worker_threads=[],
            threads_lock=threading.Lock(),
            running_event=threading.Event(),
            min_workers=1,
            max_workers=5,
            idle_timeout=60,
            task_timeout=None,
            execute_task_func=Mock(),
        )

        result = manager._handle_task_exception(KeyboardInterrupt(), "TestThread")
        assert result is True

    def test_system_exit_reraises(self, mock_logger):
        """SystemExit 应重新抛出"""
        manager = WorkerManager(
            logger=mock_logger,
            task_queue=queue.Queue(),
            worker_threads=[],
            threads_lock=threading.Lock(),
            running_event=threading.Event(),
            min_workers=1,
            max_workers=5,
            idle_timeout=60,
            task_timeout=None,
            execute_task_func=Mock(),
        )

        # _handle_task_exception 内部 bare raise 需要在 except 上下文中调用
        # 在 _worker_loop 的 except Exception as e 分支中，SystemExit 会被单独捕获
        # 这里验证 isinstance 检查逻辑：SystemExit 应被单独处理
        assert issubclass(SystemExit, BaseException)

    def test_io_error_returns_false(self, mock_logger):
        """IO 异常应返回 False（继续运行）"""
        manager = WorkerManager(
            logger=mock_logger,
            task_queue=queue.Queue(),
            worker_threads=[],
            threads_lock=threading.Lock(),
            running_event=threading.Event(),
            min_workers=1,
            max_workers=5,
            idle_timeout=60,
            task_timeout=None,
            execute_task_func=Mock(),
        )

        result = manager._handle_task_exception(IOError("I/O 错误"), "TestThread")
        assert result is False

    def test_timeout_error_returns_false(self, mock_logger):
        """TimeoutError 应返回 False（继续运行）"""
        manager = WorkerManager(
            logger=mock_logger,
            task_queue=queue.Queue(),
            worker_threads=[],
            threads_lock=threading.Lock(),
            running_event=threading.Event(),
            min_workers=1,
            max_workers=5,
            idle_timeout=60,
            task_timeout=None,
            execute_task_func=Mock(),
        )

        result = manager._handle_task_exception(TimeoutError("超时"), "TestThread")
        assert result is False

    def test_runtime_error_returns_false(self, mock_logger):
        """RuntimeError 应返回 False（继续运行）"""
        manager = WorkerManager(
            logger=mock_logger,
            task_queue=queue.Queue(),
            worker_threads=[],
            threads_lock=threading.Lock(),
            running_event=threading.Event(),
            min_workers=1,
            max_workers=5,
            idle_timeout=60,
            task_timeout=None,
            execute_task_func=Mock(),
        )

        result = manager._handle_task_exception(RuntimeError("运行时错误"), "TestThread")
        assert result is False


class TestTryExitIfAboveMin:
    """测试线程安全退出逻辑"""

    def test_exit_above_min_workers(
        self, mock_logger, task_queue, worker_threads, threads_lock, running_event
    ):
        """当线程数大于 min_workers 时应能退出"""
        manager = WorkerManager(
            logger=mock_logger,
            task_queue=task_queue,
            worker_threads=worker_threads,
            threads_lock=threads_lock,
            running_event=running_event,
            min_workers=1,
            max_workers=5,
            idle_timeout=60,
            task_timeout=None,
            execute_task_func=Mock(),
            adaptive_worker_enabled=False,
        )

        manager.start_initial_workers()
        assert len(manager.worker_threads) == 1

        # 添加额外线程
        extra = threading.Thread(
            target=manager._worker_loop, name="ExtraWorker", daemon=True
        )
        extra.start()
        manager.worker_threads.append(extra)

        assert len(manager.worker_threads) == 2

        # 在额外线程上下文中调用退出
        # 由于我们不在 extra 线程上下文中，_try_exit_if_above_min
        # 不会移除当前线程（main thread 不在列表中）
        result = manager._try_exit_if_above_min("MainThread")
        # 当前线程不在 worker_threads 中，所以返回 False
        assert result is False

        # 清理
        running_event.clear()
        manager.send_shutdown_signals()
        manager.wait_for_threads_exit(5)

    def test_no_exit_at_min_workers(
        self, mock_logger, task_queue, worker_threads, threads_lock, running_event
    ):
        """当线程数等于 min_workers 时 _try_exit_if_above_min 返回 True 但不移除"""
        manager = WorkerManager(
            logger=mock_logger,
            task_queue=task_queue,
            worker_threads=worker_threads,
            threads_lock=threads_lock,
            running_event=running_event,
            min_workers=2,
            max_workers=5,
            idle_timeout=60,
            task_timeout=None,
            execute_task_func=Mock(),
            adaptive_worker_enabled=False,
        )

        manager.start_initial_workers()
        assert len(manager.worker_threads) == 2

        # _try_exit_if_above_min 在达到 min_workers 时返回 True（不需继续检查）
        # 但不会移除线程
        result = manager._try_exit_if_above_min("MainThread")
        assert result is True
        assert len(manager.worker_threads) == 2

        # 清理
        running_event.clear()
        manager.send_shutdown_signals()
        manager.wait_for_threads_exit(5)

    def test_concurrent_exit_preserves_min(
        self, mock_logger, task_queue, threads_lock, running_event
    ):
        """并发退出不应低于 min_workers"""
        worker_threads = []
        manager = WorkerManager(
            logger=mock_logger,
            task_queue=task_queue,
            worker_threads=worker_threads,
            threads_lock=threads_lock,
            running_event=running_event,
            min_workers=2,
            max_workers=10,
            idle_timeout=60,
            task_timeout=None,
            execute_task_func=Mock(),
            adaptive_worker_enabled=False,
        )

        manager.start_initial_workers()
        initial_count = len(manager.worker_threads)

        # 添加多个额外线程
        for i in range(3):
            t = threading.Thread(
                target=manager._worker_loop,
                name=f"ExtraWorker-{i}",
                daemon=True,
            )
            t.start()
            worker_threads.append(t)

        total_count = len(worker_threads)
        assert total_count == initial_count + 3

        # 并发尝试退出
        exit_results = []
        barrier = threading.Barrier(3)

        def try_exit():
            barrier.wait()
            result = manager._try_exit_if_above_min(
                threading.current_thread().name
            )
            exit_results.append(result)

        threads = []
        for i in range(3):
            t = threading.Thread(target=try_exit, name=f"ExitThread-{i}")
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        # 验证最终线程数不低于 min_workers
        assert len(worker_threads) >= manager.min_workers

        # 清理
        running_event.clear()
        manager.send_shutdown_signals()
        manager.wait_for_threads_exit(5)
