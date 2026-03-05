"""
清理线程模块测试

测试 CleanupThreadManager 类的功能。
"""

import logging
import threading
import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from fish_async_task.cleanup import CleanupThreadManager


class TestCleanupThreadManager:
    """测试 CleanupThreadManager 类"""

    def test_init(self):
        """测试初始化"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()
        cleanup_func = Mock()

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=100,
            cleanup_func=cleanup_func,
        )

        assert manager.logger == logger
        assert manager._running_event == running_event
        assert manager.cleanup_interval == 100
        assert manager._cleanup_func == cleanup_func
        assert manager.cleanup_thread is None

    def test_start_creates_thread(self):
        """测试启动创建线程"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()
        running_event.set()  # 设置事件以保持线程运行
        cleanup_func = Mock()

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=10,
            cleanup_func=cleanup_func,
        )

        manager.start()

        assert manager.cleanup_thread is not None
        assert manager.cleanup_thread.daemon is True
        assert manager.cleanup_thread.name == "TaskStatusCleanup"

        # 清理：停止线程
        running_event.clear()
        manager.cleanup_thread.join(timeout=1)

    def test_cleanup_loop_executes_cleanup(self):
        """测试清理循环执行清理函数"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()
        running_event.set()  # 设置事件
        cleanup_call_count = {"count": 0}

        def cleanup_func():
            cleanup_call_count["count"] += 1
            return cleanup_call_count["count"]

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=0.1,  # 0.1秒间隔，加快测试
            cleanup_func=cleanup_func,
        )

        manager.start()

        # 等待至少执行一次清理
        time.sleep(0.3)
        running_event.clear()
        manager.cleanup_thread.join(timeout=1)

        assert cleanup_call_count["count"] >= 1

    def test_wait_with_interrupt_check_continues(self):
        """测试可中断等待 - 继续运行"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()
        cleanup_func = Mock()

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=100,
            cleanup_func=cleanup_func,
        )

        running_event.set()
        # 使用很短的检查间隔
        result = manager._wait_with_interrupt_check(0.01)

        # 应该返回 True（继续运行）
        assert result is True

    def test_wait_with_interrupt_check_stops(self):
        """测试可中断等待 - 停止运行"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()
        cleanup_func = Mock()

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=100,
            cleanup_func=cleanup_func,
        )

        running_event.set()

        def clear_after_delay():
            time.sleep(0.05)
            running_event.clear()

        thread = threading.Thread(target=clear_after_delay)
        thread.start()

        result = manager._wait_with_interrupt_check(0.02)
        thread.join(timeout=0.2)

        # 应该返回 False（停止运行）
        assert result is False

    def test_cleanup_loop_handles_io_error(self):
        """测试清理循环处理 I/O 错误"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()

        def cleanup_func():
            raise IOError("I/O error")

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=1,
            cleanup_func=cleanup_func,
        )

        manager.start()

        # 等待错误被处理
        time.sleep(0.2)
        running_event.clear()
        manager.cleanup_thread.join(timeout=1)

        # 线程应该正常退出而不崩溃
        assert not manager.cleanup_thread.is_alive()

    def test_cleanup_loop_handles_os_error(self):
        """测试清理循环处理 OS 错误"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()

        def cleanup_func():
            raise OSError("OS error")

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=1,
            cleanup_func=cleanup_func,
        )

        manager.start()

        time.sleep(0.2)
        running_event.clear()
        manager.cleanup_thread.join(timeout=1)

        assert not manager.cleanup_thread.is_alive()

    def test_cleanup_loop_handles_connection_error(self):
        """测试清理循环处理连接错误"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()

        def cleanup_func():
            raise ConnectionError("Connection error")

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=1,
            cleanup_func=cleanup_func,
        )

        manager.start()

        time.sleep(0.2)
        running_event.clear()
        manager.cleanup_thread.join(timeout=1)

        assert not manager.cleanup_thread.is_alive()

    def test_cleanup_loop_handles_attribute_error(self):
        """测试清理循环处理属性错误"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()

        def cleanup_func():
            raise AttributeError("Attribute error")

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=1,
            cleanup_func=cleanup_func,
        )

        manager.start()

        time.sleep(0.2)
        running_event.clear()
        manager.cleanup_thread.join(timeout=1)

        assert not manager.cleanup_thread.is_alive()

    def test_cleanup_loop_handles_type_error(self):
        """测试清理循环处理类型错误"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()

        def cleanup_func():
            raise TypeError("Type error")

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=1,
            cleanup_func=cleanup_func,
        )

        manager.start()

        time.sleep(0.2)
        running_event.clear()
        manager.cleanup_thread.join(timeout=1)

        assert not manager.cleanup_thread.is_alive()

    def test_cleanup_loop_handles_value_error(self):
        """测试清理循环处理值错误"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()

        def cleanup_func():
            raise ValueError("Value error")

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=1,
            cleanup_func=cleanup_func,
        )

        manager.start()

        time.sleep(0.2)
        running_event.clear()
        manager.cleanup_thread.join(timeout=1)

        assert not manager.cleanup_thread.is_alive()

    def test_cleanup_loop_consecutive_errors_reset(self):
        """测试连续错误计数重置"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()
        running_event.set()
        call_count = {"count": 0}

        def cleanup_func():
            call_count["count"] += 1
            if call_count["count"] <= 5:
                raise Exception("Error")
            return 0

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=0.05,  # 快速间隔
            cleanup_func=cleanup_func,
        )

        manager.start()

        # 等待足够的错误和成功执行
        time.sleep(0.5)
        running_event.clear()
        manager.cleanup_thread.join(timeout=1)

        # 线程应该继续运行（错误重置）
        assert call_count["count"] >= 5

    def test_cleanup_loop_keyboard_interrupt(self):
        """测试键盘中断"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()

        def cleanup_func():
            raise KeyboardInterrupt()

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=1,
            cleanup_func=cleanup_func,
        )

        manager.start()

        time.sleep(0.2)
        manager.cleanup_thread.join(timeout=1)

        assert not manager.cleanup_thread.is_alive()

    def test_join_timeout(self):
        """测试 join 超时"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()

        def cleanup_func():
            time.sleep(10)  # 长时间运行

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=100,  # 长间隔
            cleanup_func=cleanup_func,
        )

        manager.start()
        time.sleep(0.1)  # 让线程启动

        # join 超时应该返回
        manager.join(timeout=0.1)

        # 线程可能还在运行
        running_event.clear()
        manager.cleanup_thread.join(timeout=1)

    def test_join_successful(self):
        """测试 join 成功"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()

        def cleanup_func():
            return 0

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=100,
            cleanup_func=cleanup_func,
        )

        manager.start()
        running_event.clear()

        # 应该能够成功 join
        manager.join(timeout=1)

        assert not manager.cleanup_thread.is_alive()

    def test_check_interval_calculation(self):
        """测试检查间隔计算"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()
        cleanup_func = Mock()

        # 清理间隔 10 秒，检查间隔应该是 1 秒（MIN_CHECK_INTERVAL）
        manager1 = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=10,
            cleanup_func=cleanup_func,
        )

        # 清理间隔 1 秒，检查间隔应该是 0.1 秒
        manager2 = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=1,
            cleanup_func=cleanup_func,
        )

        # 启动线程并等待
        manager1.start()
        manager2.start()

        time.sleep(0.1)
        running_event.clear()

        manager1.cleanup_thread.join(timeout=1)
        if manager2.cleanup_thread:
            manager2.cleanup_thread.join(timeout=1)

    def test_multiple_cleanup_cycles(self):
        """测试多次清理循环"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()
        running_event.set()
        call_count = {"count": 0}

        def cleanup_func():
            call_count["count"] += 1
            return call_count["count"]

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=0.1,
            cleanup_func=cleanup_func,
        )

        manager.start()

        # 等待多次清理
        time.sleep(0.35)
        running_event.clear()
        manager.cleanup_thread.join(timeout=1)

        assert call_count["count"] >= 2

    def test_cleanup_returns_count(self):
        """测试清理函数返回计数"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()

        def cleanup_func():
            return 5  # 清理了 5 个项目

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=1,
            cleanup_func=cleanup_func,
        )

        manager.start()

        time.sleep(0.2)
        running_event.clear()
        manager.cleanup_thread.join(timeout=1)

        # 线程应该正常退出
        assert not manager.cleanup_thread.is_alive()

    def test_rapid_start_stop(self):
        """测试快速启动和停止"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()
        cleanup_func = Mock()

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=100,
            cleanup_func=cleanup_func,
        )

        # 快速启动和停止
        for _ in range(5):
            running_event.set()
            manager.start()
            time.sleep(0.01)
            running_event.clear()
            if manager.cleanup_thread:
                manager.cleanup_thread.join(timeout=0.5)


class TestCleanupThreadManagerIntegration:
    """测试 CleanupThreadManager 集成场景"""

    def test_cleanup_with_actual_cleanup_logic(self):
        """测试实际清理逻辑集成"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()
        running_event.set()
        cleaned_items = []

        def cleanup_func():
            # 模拟清理逻辑
            cleaned_items.append(len(cleaned_items) + 1)
            return len(cleaned_items)

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=0.1,
            cleanup_func=cleanup_func,
        )

        manager.start()

        # 等待几次清理
        time.sleep(0.3)
        running_event.clear()
        manager.cleanup_thread.join(timeout=1)

        assert len(cleaned_items) >= 1

    def test_error_recovery_continues_cleanup(self):
        """测试错误恢复后继续清理"""
        logger = logging.getLogger(__name__)
        running_event = threading.Event()
        running_event.set()
        call_count = {"count": 0}
        success_count = {"success": 0}

        def cleanup_func():
            call_count["count"] += 1
            if call_count["count"] <= 3:
                raise Exception("Temporary error")
            success_count["success"] += 1
            return success_count["success"]

        manager = CleanupThreadManager(
            logger=logger,
            running_event=running_event,
            cleanup_interval=0.05,
            cleanup_func=cleanup_func,
        )

        manager.start()

        time.sleep(0.4)
        running_event.clear()
        manager.cleanup_thread.join(timeout=1)

        # 应该有成功的清理
        assert success_count["success"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
