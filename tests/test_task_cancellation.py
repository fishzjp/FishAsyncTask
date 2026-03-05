"""
任务取消模块测试

优化策略：
1. 移除不必要的 time.sleep()，使用 Mock 或直接调用
2. 使用更短的等待时间
3. 将必须等待的测试标记为慢速测试
"""

import threading
import time
from unittest.mock import Mock, patch

import pytest

from fish_async_task.performance.task_cancellation import (
    CancelEvent,
    CancellableTask,
    TaskCancellationManager,
    check_cancelled_periodically,
    create_cancellable_task,
)


class TestCancelEvent:
    """测试 CancelEvent 类"""

    def test_init(self):
        """测试初始化"""
        event = CancelEvent()
        assert not event.is_cancelled()

    def test_cancel(self):
        """测试取消"""
        event = CancelEvent()
        event.cancel()
        assert event.is_cancelled()

    def test_wait(self):
        """测试等待"""
        event = CancelEvent()

        def delayed_cancel():
            event.cancel()

        thread = threading.Thread(target=delayed_cancel)
        thread.start()
        thread.join(timeout=0.1)  # 等待线程完成
        assert event.wait(timeout=0.5)

    def test_wait_timeout(self):
        """测试等待超时"""
        event = CancelEvent()
        assert not event.wait(timeout=0.01)  # 使用更短的超时时间

    def test_reset(self):
        """测试重置"""
        event = CancelEvent()
        event.cancel()
        assert event.is_cancelled()
        event.reset()
        assert not event.is_cancelled()


class TestCancellableTask:
    """测试 CancellableTask 类"""

    def test_init(self):
        """测试初始化"""

        def task_func():
            return "result"

        task = CancellableTask("task1", task_func)
        assert task.task_id == "task1"
        assert task.func == task_func
        assert task.args == ()
        assert task.kwargs == {}
        assert not task.is_completed()
        assert not task.is_started()

    def test_init_with_args(self):
        """测试带参数的初始化"""

        def task_func(a, b):
            return a + b

        task = CancellableTask("task1", task_func, args=(1, 2))
        assert task.args == (1, 2)

    def test_init_with_kwargs(self):
        """测试带关键字参数的初始化"""

        def task_func(a, b):
            return a + b

        task = CancellableTask("task1", task_func, kwargs={"a": 1, "b": 2})
        assert task.kwargs == {"a": 1, "b": 2}

    def test_execute_success(self):
        """测试成功执行"""

        def task_func(cancel_event=None):
            return "result"

        task = CancellableTask("task1", task_func)
        result = task.execute()
        assert result == "result"
        assert task.is_completed()
        assert task.is_started()

    def test_execute_cancelled_before(self):
        """测试执行前取消"""

        def task_func(cancel_event=None):
            return "result"

        task = CancellableTask("task1", task_func)
        task.cancel_event.cancel()
        result = task.execute()
        assert result is None

    def test_execute_with_cancel_check(self):
        """测试带取消检查的执行"""

        def task_func(cancel_event=None):
            for i in range(10):  # 减少循环次数
                if cancel_event and cancel_event.is_cancelled():
                    return "cancelled"
                # 移除 sleep，直接检查取消状态
            return "completed"

        task = CancellableTask("task1", task_func)

        def delayed_cancel():
            task.cancel_event.cancel()

        thread = threading.Thread(target=delayed_cancel)
        thread.start()
        # 等待一点时间让线程启动
        thread.join(timeout=0.01)
        result = task.execute()
        assert result == "cancelled"

    def test_execute_exception(self):
        """测试执行异常"""

        def task_func(cancel_event=None):
            raise ValueError("Test error")

        task = CancellableTask("task1", task_func)
        with pytest.raises(ValueError, match="Test error"):
            task.execute()
        assert task.is_completed()

    def test_cancel(self):
        """测试取消任务"""

        def long_running_task(cancel_event=None):
            for i in range(100):  # 减少循环次数
                if cancel_event and cancel_event.is_cancelled():
                    return "cancelled"
                # 移除 sleep
            return "completed"

        task = CancellableTask("task1", long_running_task)

        def delayed_cancel():
            task.cancel()

        thread = threading.Thread(target=delayed_cancel)
        thread.start()
        thread.join(timeout=0.01)
        result = task.execute()
        assert result == "cancelled"

    def test_cancel_completed_task(self):
        """测试取消已完成的任务"""

        def task_func(cancel_event=None):
            return "result"

        task = CancellableTask("task1", task_func)
        task.execute()
        assert not task.cancel()  # 已完成的任务无法取消

    def test_get_result(self):
        """测试获取结果"""

        def task_func(cancel_event=None):
            return "result"

        task = CancellableTask("task1", task_func)
        task.execute()
        result = task.get_result()
        assert result == "result"

    def test_get_result_timeout(self):
        """测试获取结果超时"""

        def slow_task(cancel_event=None):
            time.sleep(0.1)  # 减少等待时间
            return "result"

        task = CancellableTask("task1", slow_task)
        # 在另一个线程中运行任务
        import threading

        thread = threading.Thread(target=task.execute)
        thread.start()

        # 等待时间应该小于任务执行时间
        with pytest.raises(TimeoutError):
            task.get_result(timeout=0.01)

        thread.join(timeout=0.2)  # 清理线程

    def test_get_result_exception(self):
        """测试获取异常结果"""

        def task_func(cancel_event=None):
            raise ValueError("Test error")

        task = CancellableTask("task1", task_func)
        # execute() 会抛出异常，所以我们需要在另一个线程中运行
        import threading

        thread = threading.Thread(target=task.execute)
        thread.start()
        thread.join()

        # 现在任务已完成，可以获取结果（应该抛出异常）
        with pytest.raises(ValueError, match="Test error"):
            task.get_result()


class TestTaskCancellationManager:
    """测试 TaskCancellationManager 类"""

    def test_init(self):
        """测试初始化"""
        manager = TaskCancellationManager()
        assert manager.get_active_count() == 0

    def test_register_task(self):
        """测试注册任务"""
        manager = TaskCancellationManager()

        def task_func(cancel_event=None):
            return "result"

        token = manager.register_task("task1", task_func)
        assert token is not None
        assert not token.is_cancelled()
        assert manager.get_active_count() == 1

    def test_register_task_overwrite(self):
        """测试覆盖已存在的任务"""
        manager = TaskCancellationManager()

        def task_func(cancel_event=None):
            return "result"

        manager.register_task("task1", task_func)
        manager.register_task("task1", task_func)  # 覆盖
        assert manager.get_active_count() == 1

    def test_cancel_task(self):
        """测试取消任务"""
        manager = TaskCancellationManager()

        def task_func(cancel_event=None):
            time.sleep(1.0)
            return "result"

        manager.register_task("task1", task_func)
        result = manager.cancel_task("task1")
        assert result is True
        assert manager.get_active_count() == 0

    def test_cancel_nonexistent_task(self):
        """测试取消不存在的任务"""
        manager = TaskCancellationManager()
        result = manager.cancel_task("nonexistent")
        assert result is False

    def test_cancel_all(self):
        """测试取消所有任务"""
        manager = TaskCancellationManager()

        def task_func(cancel_event=None):
            return "result"

        manager.register_task("task1", task_func)
        manager.register_task("task2", task_func)
        manager.register_task("task3", task_func)

        count = manager.cancel_all()
        assert count == 3
        assert manager.get_active_count() == 0

    def test_get_cancel_token(self):
        """测试获取取消令牌"""
        manager = TaskCancellationManager()

        def task_func(cancel_event=None):
            return "result"

        manager.register_task("task1", task_func)
        token = manager.get_cancel_token("task1")
        assert token is not None
        assert manager.get_cancel_token("nonexistent") is None

    def test_is_task_cancelled(self):
        """测试检查任务是否已取消"""
        manager = TaskCancellationManager()

        def task_func(cancel_event=None):
            return "result"

        manager.register_task("task1", task_func)
        assert not manager.is_task_cancelled("task1")

        token = manager.get_cancel_token("task1")
        token.cancel()
        assert manager.is_task_cancelled("task1")

    def test_is_task_completed(self):
        """测试检查任务是否已完成"""
        manager = TaskCancellationManager()

        def task_func(cancel_event=None):
            return "result"

        task = CancellableTask("task1", task_func)
        manager.register_task("task1", task_func)
        assert not manager.is_task_completed("task1")

        task.execute()
        assert manager.is_task_completed("task1")

    def test_get_active_count(self):
        """测试获取活跃任务数量"""
        manager = TaskCancellationManager()

        def task_func(cancel_event=None):
            return "result"

        assert manager.get_active_count() == 0
        manager.register_task("task1", task_func)
        assert manager.get_active_count() == 1
        manager.register_task("task2", task_func)
        assert manager.get_active_count() == 2

    def test_get_stats(self):
        """测试获取统计信息"""
        manager = TaskCancellationManager()

        def task_func(cancel_event=None):
            return "result"

        manager.register_task("task1", task_func)
        task = CancellableTask("task2", task_func)
        manager.register_task("task2", task_func)
        task.execute()  # 完成 task2

        stats = manager.get_stats()
        assert stats["total_tracked"] == 2
        assert stats["active"] == 1
        assert stats["completed"] == 1


class TestUtilityFunctions:
    """测试工具函数"""

    def test_create_cancellable_task_no_event(self):
        """测试创建没有取消事件的任务"""

        def task_func():
            return "result"

        wrapper = create_cancellable_task(task_func)
        assert wrapper() == "result"

    def test_create_cancellable_task_with_event(self):
        """测试创建带取消事件的任务"""

        def task_func():
            return "result"

        event = CancelEvent()
        wrapper = create_cancellable_task(task_func, event)
        assert wrapper() == "result"

    def test_create_cancellable_task_cancelled(self):
        """测试创建已取消的任务"""

        def task_func():
            return "result"

        event = CancelEvent()
        event.cancel()
        wrapper = create_cancellable_task(task_func, event)
        assert wrapper() is None

    def test_check_cancelled_periodically_none(self):
        """测试周期性检查 - 无事件"""
        assert not check_cancelled_periodically(None)

    def test_check_cancelled_periodically_not_cancelled(self):
        """测试周期性检查 - 未取消"""
        event = CancelEvent()
        assert not check_cancelled_periodically(event, check_interval=10)

    def test_check_cancelled_periodically_cancelled(self):
        """测试周期性检查 - 已取消"""
        event = CancelEvent()
        event.cancel()
        assert check_cancelled_periodically(event, check_interval=10)

    def test_check_cancelled_periodically_with_counter(self):
        """测试周期性检查 - 计数器"""
        event = CancelEvent()

        def delayed_cancel():
            event.cancel()

        thread = threading.Thread(target=delayed_cancel)
        thread.start()
        thread.join(timeout=0.01)

        # 运行多次检查，最终应该检测到取消
        for _ in range(5):  # 减少循环次数
            if check_cancelled_periodically(event, check_interval=2):
                assert True
                break
        else:
            assert False, "Should have detected cancellation"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
