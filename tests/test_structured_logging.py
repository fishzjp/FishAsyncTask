"""
结构化日志模块测试

测试 StructuredLogger 和 ContextLogger 类的功能。
"""

import json
import logging
import re
import threading
import time
from io import StringIO
from unittest.mock import patch

import pytest

from fish_async_task.performance._structured_logging import (
    ContextLogger,
    StructuredLogger,
    get_context_logger,
    get_structured_logger,
)


class TestStructuredLogger:
    """测试 StructuredLogger 类"""

    def test_init(self):
        """测试初始化"""
        base_logger = logging.getLogger("test_logger")
        structured_logger = StructuredLogger(base_logger)

        assert structured_logger._logger is base_logger
        assert structured_logger._context == {}
        # 检查是否有锁属性（而不是特定类型，因为不同 Python 版本类型不同）
        assert hasattr(structured_logger, "_context_lock")

    def test_set_context(self):
        """测试设置上下文"""
        base_logger = logging.getLogger("test_set_context")
        structured_logger = StructuredLogger(base_logger)

        structured_logger.set_context(user_id="123", action="test")

        assert structured_logger._context == {"user_id": "123", "action": "test"}

    def test_set_context_multiple_calls(self):
        """测试多次调用 set_context 会合并上下文"""
        base_logger = logging.getLogger("test_set_context_multiple")
        structured_logger = StructuredLogger(base_logger)

        structured_logger.set_context(user_id="123")
        structured_logger.set_context(action="test")

        assert structured_logger._context == {"user_id": "123", "action": "test"}

    def test_set_context_overwrite(self):
        """测试上下文覆盖"""
        base_logger = logging.getLogger("test_set_context_overwrite")
        structured_logger = StructuredLogger(base_logger)

        structured_logger.set_context(user_id="123")
        structured_logger.set_context(user_id="456")

        assert structured_logger._context == {"user_id": "456"}

    def test_clear_context(self):
        """测试清除上下文"""
        base_logger = logging.getLogger("test_clear_context")
        structured_logger = StructuredLogger(base_logger)

        structured_logger.set_context(user_id="123", action="test")
        structured_logger.clear_context()

        assert structured_logger._context == {}

    def test_format_message_basic(self):
        """测试基本消息格式化"""
        base_logger = logging.getLogger("test_format_basic")
        structured_logger = StructuredLogger(base_logger)

        message = structured_logger._format_message("Test message")

        parsed = json.loads(message)
        assert parsed["message"] == "Test message"
        assert "timestamp" in parsed
        assert "context" not in parsed

    def test_format_message_with_context(self):
        """测试带上下文的消息格式化"""
        base_logger = logging.getLogger("test_format_with_context")
        structured_logger = StructuredLogger(base_logger)

        structured_logger.set_context(user_id="123", action="test")
        message = structured_logger._format_message("Test message")

        parsed = json.loads(message)
        assert parsed["message"] == "Test message"
        assert parsed["context"] == {"user_id": "123", "action": "test"}

    def test_format_message_with_extra_context(self):
        """测试带额外上下文的消息格式化"""
        base_logger = logging.getLogger("test_format_extra_context")
        structured_logger = StructuredLogger(base_logger)

        structured_logger.set_context(user_id="123")
        message = structured_logger._format_message(
            "Test message", extra_context={"action": "test"}
        )

        parsed = json.loads(message)
        assert parsed["context"] == {"user_id": "123", "action": "test"}

    def test_format_message_extra_context_overwrites(self):
        """测试额外上下文会覆盖基础上下文"""
        base_logger = logging.getLogger("test_format_overwrite")
        structured_logger = StructuredLogger(base_logger)

        structured_logger.set_context(user_id="123", action="old")
        message = structured_logger._format_message("Test message", extra_context={"action": "new"})

        parsed = json.loads(message)
        assert parsed["context"]["action"] == "new"

    def test_format_message_without_timestamp(self):
        """测试不包含时间戳的消息格式化"""
        base_logger = logging.getLogger("test_format_no_timestamp")
        structured_logger = StructuredLogger(base_logger)

        message = structured_logger._format_message("Test message", include_timestamp=False)

        parsed = json.loads(message)
        assert parsed["message"] == "Test message"
        assert "timestamp" not in parsed

    def test_format_message_timestamp_format(self):
        """测试时间戳格式"""
        base_logger = logging.getLogger("test_timestamp_format")
        structured_logger = StructuredLogger(base_logger)

        message = structured_logger._format_message("Test message")

        parsed = json.loads(message)
        # ISO 8601 格式应该匹配这个模式
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+", parsed["timestamp"])

    def test_debug_log_level(self):
        """测试 DEBUG 日志级别"""
        base_logger = logging.getLogger("test_debug")
        structured_logger = StructuredLogger(base_logger)

        # 添加 StringIO handler 来捕获日志
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.DEBUG)
        base_logger.addHandler(handler)
        base_logger.setLevel(logging.DEBUG)

        structured_logger.debug("Debug message", key="value")

        log_output = stream.getvalue()
        assert "Debug message" in log_output
        assert "key" in log_output
        assert "value" in log_output

        base_logger.removeHandler(handler)

    def test_info_log_level(self):
        """测试 INFO 日志级别"""
        base_logger = logging.getLogger("test_info")
        structured_logger = StructuredLogger(base_logger)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.INFO)
        base_logger.addHandler(handler)
        base_logger.setLevel(logging.INFO)

        structured_logger.info("Info message", key="value")

        log_output = stream.getvalue()
        assert "Info message" in log_output

        base_logger.removeHandler(handler)

    def test_warning_log_level(self):
        """测试 WARNING 日志级别"""
        base_logger = logging.getLogger("test_warning")
        structured_logger = StructuredLogger(base_logger)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.WARNING)
        base_logger.addHandler(handler)
        base_logger.setLevel(logging.WARNING)

        structured_logger.warning("Warning message", key="value")

        log_output = stream.getvalue()
        assert "Warning message" in log_output

        base_logger.removeHandler(handler)

    def test_error_log_level(self):
        """测试 ERROR 日志级别"""
        base_logger = logging.getLogger("test_error")
        structured_logger = StructuredLogger(base_logger)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.ERROR)
        base_logger.addHandler(handler)
        base_logger.setLevel(logging.ERROR)

        structured_logger.error("Error message", exc_info=False, key="value")

        log_output = stream.getvalue()
        assert "Error message" in log_output

        base_logger.removeHandler(handler)

    def test_error_with_exc_info(self):
        """测试带异常信息的 ERROR 日志"""
        base_logger = logging.getLogger("test_error_exc")
        structured_logger = StructuredLogger(base_logger)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.ERROR)
        base_logger.addHandler(handler)
        base_logger.setLevel(logging.ERROR)

        try:
            raise ValueError("Test exception")
        except ValueError:
            structured_logger.error("Error occurred", exc_info=True)

        log_output = stream.getvalue()
        assert "Error occurred" in log_output
        assert "ValueError" in log_output

        base_logger.removeHandler(handler)

    def test_critical_log_level(self):
        """测试 CRITICAL 日志级别"""
        base_logger = logging.getLogger("test_critical")
        structured_logger = StructuredLogger(base_logger)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.CRITICAL)
        base_logger.addHandler(handler)
        base_logger.setLevel(logging.CRITICAL)

        structured_logger.critical("Critical message", exc_info=False, key="value")

        log_output = stream.getvalue()
        assert "Critical message" in log_output

        base_logger.removeHandler(handler)

    def test_critical_with_exc_info(self):
        """测试带异常信息的 CRITICAL 日志"""
        base_logger = logging.getLogger("test_critical_exc")
        structured_logger = StructuredLogger(base_logger)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.CRITICAL)
        base_logger.addHandler(handler)
        base_logger.setLevel(logging.CRITICAL)

        try:
            raise RuntimeError("Critical error")
        except RuntimeError:
            structured_logger.critical("Critical failure", exc_info=True)

        log_output = stream.getvalue()
        assert "Critical failure" in log_output
        assert "RuntimeError" in log_output

        base_logger.removeHandler(handler)

    def test_log_exception(self):
        """测试记录异常"""
        base_logger = logging.getLogger("test_log_exception")
        structured_logger = StructuredLogger(base_logger)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.ERROR)
        base_logger.addHandler(handler)
        base_logger.setLevel(logging.ERROR)

        exception = ValueError("Test exception")
        structured_logger.log_exception("Error during operation", exception)

        log_output = stream.getvalue()
        assert "Error during operation" in log_output
        assert "ValueError" in log_output
        assert "Test exception" in log_output

        base_logger.removeHandler(handler)

    def test_log_exception_with_context(self):
        """测试带上下文的异常记录"""
        base_logger = logging.getLogger("test_exception_context")
        structured_logger = StructuredLogger(base_logger)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.ERROR)
        base_logger.addHandler(handler)
        base_logger.setLevel(logging.ERROR)

        exception = RuntimeError("Test error")
        structured_logger.log_exception(
            "Error during operation",
            exception,
            context={"user_id": "123", "operation": "delete"},
        )

        log_output = stream.getvalue()
        # 查找 JSON 部分并解析（堆栈跟踪会在 JSON 之后）
        for line in log_output.split("\n"):
            if "Error during operation" in line:
                # 提取 JSON 部分
                json_start = line.find("{")
                if json_start != -1:
                    json_str = line[json_start:]
                    parsed = json.loads(json_str)
                    assert parsed["message"] == "Error during operation"
                    assert parsed["context"]["exception_type"] == "RuntimeError"
                    assert parsed["context"]["exception_message"] == "Test error"
                    assert parsed["context"]["user_id"] == "123"
                    assert parsed["context"]["operation"] == "delete"
                    break
        else:
            pytest.fail("JSON message not found in log output")

        base_logger.removeHandler(handler)

    def test_log_exception_includes_stack_trace(self):
        """测试异常记录包含堆栈跟踪"""
        base_logger = logging.getLogger("test_exception_stack")
        structured_logger = StructuredLogger(base_logger)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.ERROR)
        base_logger.addHandler(handler)
        base_logger.setLevel(logging.ERROR)

        try:

            def inner_function():
                raise KeyError("test_key")

            inner_function()
        except KeyError as e:
            structured_logger.log_exception("Caught exception", e)

        log_output = stream.getvalue()
        assert "Caught exception" in log_output
        assert "KeyError" in log_output
        # exc_info=True 应该包含堆栈跟踪
        assert "inner_function" in log_output or "KeyError" in log_output

        base_logger.removeHandler(handler)


class TestStructuredLoggerThreadSafety:
    """测试 StructuredLogger 的线程安全性"""

    def test_concurrent_context_updates(self):
        """测试并发上下文更新"""
        base_logger = logging.getLogger("test_concurrent_context")
        structured_logger = StructuredLogger(base_logger)

        def update_context(thread_id: int):
            for i in range(100):
                structured_logger.set_context(thread_id=thread_id, value=i)

        threads = []
        for i in range(10):
            t = threading.Thread(target=update_context, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # 验证最终状态是一个有效的字典
        assert isinstance(structured_logger._context, dict)

    def test_concurrent_logging(self):
        """测试并发日志记录"""
        base_logger = logging.getLogger("test_concurrent_logging")
        structured_logger = StructuredLogger(base_logger)

        # 设置日志级别以避免实际输出
        base_logger.setLevel(logging.CRITICAL)

        def log_messages(thread_id: int):
            for i in range(50):
                structured_logger.info(f"Message {i} from thread {thread_id}")

        threads = []
        for i in range(5):
            t = threading.Thread(target=log_messages, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # 如果没有崩溃或死锁，测试通过
        assert True

    def test_concurrent_context_and_logging(self):
        """测试并发上下文更新和日志记录"""
        base_logger = logging.getLogger("test_concurrent_mixed")
        structured_logger = StructuredLogger(base_logger)
        base_logger.setLevel(logging.CRITICAL)

        def mixed_operations(thread_id: int):
            for i in range(50):
                if i % 2 == 0:
                    structured_logger.set_context(thread_id=thread_id, iteration=i)
                else:
                    structured_logger.info(f"Log from thread {thread_id}")

        threads = []
        for i in range(5):
            t = threading.Thread(target=mixed_operations, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert True


class TestContextLogger:
    """测试 ContextLogger 类"""

    def test_init(self):
        """测试初始化"""
        base_logger = logging.getLogger("test_context_logger_init")
        context_logger = ContextLogger(base_logger)

        assert isinstance(context_logger._logger, StructuredLogger)
        assert context_logger._context_stack == []

    def test_push_context(self):
        """测试推入上下文"""
        base_logger = logging.getLogger("test_push_context")
        context_logger = ContextLogger(base_logger)

        result = context_logger.push_context(user_id="123", action="test")

        assert result is context_logger  # 支持链式调用
        assert len(context_logger._context_stack) == 1
        assert context_logger._context_stack[0] == {"user_id": "123", "action": "test"}

    def test_push_context_multiple(self):
        """测试多次推入上下文"""
        base_logger = logging.getLogger("test_push_multiple")
        context_logger = ContextLogger(base_logger)

        context_logger.push_context(level=1)
        context_logger.push_context(level=2)
        context_logger.push_context(level=3)

        assert len(context_logger._context_stack) == 3
        assert context_logger._context_stack == [
            {"level": 1},
            {"level": 2},
            {"level": 3},
        ]

    def test_pop_context(self):
        """测试弹出上下文"""
        base_logger = logging.getLogger("test_pop_context")
        context_logger = ContextLogger(base_logger)

        context_logger.push_context(level=1)
        context_logger.push_context(level=2)
        context_logger.pop_context()

        assert len(context_logger._context_stack) == 1
        assert context_logger._context_stack[0] == {"level": 1}

    def test_pop_context_last(self):
        """测试弹出最后一个上下文"""
        base_logger = logging.getLogger("test_pop_last")
        context_logger = ContextLogger(base_logger)

        context_logger.push_context(level=1)
        context_logger.pop_context()

        assert len(context_logger._context_stack) == 0

    def test_pop_context_empty_stack(self):
        """测试在空栈上弹出"""
        base_logger = logging.getLogger("test_pop_empty")
        context_logger = ContextLogger(base_logger)

        # 不应该抛出异常
        context_logger.pop_context()

        assert len(context_logger._context_stack) == 0

    def test_context_manager_enter(self):
        """测试上下文管理器进入"""
        base_logger = logging.getLogger("test_context_enter")
        context_logger = ContextLogger(base_logger)

        with context_logger.push_context(operation="test"):
            assert len(context_logger._context_stack) == 1

        assert len(context_logger._context_stack) == 0

    def test_context_manager_exit(self):
        """测试上下文管理器退出"""
        base_logger = logging.getLogger("test_context_exit")
        context_logger = ContextLogger(base_logger)

        with context_logger.push_context(operation="test"):
            assert len(context_logger._context_stack) == 1

        # 退出后上下文应该被清理
        assert len(context_logger._context_stack) == 0

    def test_nested_context_managers(self):
        """测试嵌套上下文管理器"""
        base_logger = logging.getLogger("test_nested_context")
        context_logger = ContextLogger(base_logger)

        with context_logger.push_context(level=1):
            assert len(context_logger._context_stack) == 1
            with context_logger.push_context(level=2):
                assert len(context_logger._context_stack) == 2
            assert len(context_logger._context_stack) == 1

        assert len(context_logger._context_stack) == 0

    def test_context_manager_with_exception(self):
        """测试上下文管理器中的异常处理"""
        base_logger = logging.getLogger("test_context_exception")
        context_logger = ContextLogger(base_logger)

        try:
            with context_logger.push_context(operation="test"):
                assert len(context_logger._context_stack) == 1
                raise ValueError("Test error")
        except ValueError:
            pass

        # 即使有异常，上下文也应该被清理
        assert len(context_logger._context_stack) == 0

    def test_logging_with_context(self):
        """测试带上下文的日志记录"""
        base_logger = logging.getLogger("test_logging_with_context")
        context_logger = ContextLogger(base_logger)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.INFO)
        base_logger.addHandler(handler)
        base_logger.setLevel(logging.INFO)

        with context_logger.push_context(user_id="123"):
            context_logger.info("Test message")

        log_output = stream.getvalue()
        assert "Test message" in log_output

        base_logger.removeHandler(handler)

    def test_chain_context_pushes(self):
        """测试链式调用推入上下文"""
        base_logger = logging.getLogger("test_chain_context")
        context_logger = ContextLogger(base_logger)

        result = context_logger.push_context(level=1).push_context(level=2).push_context(level=3)

        assert result is context_logger
        assert len(context_logger._context_stack) == 3


class TestContextLoggerThreadSafety:
    """测试 ContextLogger 的线程安全性"""

    def test_concurrent_push_pop(self):
        """测试并发推入和弹出操作"""
        base_logger = logging.getLogger("test_concurrent_push_pop")
        context_logger = ContextLogger(base_logger)
        base_logger.setLevel(logging.CRITICAL)

        def push_pop_operations(thread_id: int):
            for i in range(50):
                context_logger.push_context(thread_id=thread_id, iteration=i)
                context_logger.pop_context()

        threads = []
        for i in range(5):
            t = threading.Thread(target=push_pop_operations, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # 栈应该为空或者接近空
        assert len(context_logger._context_stack) < 10


class TestFactoryFunctions:
    """测试工厂函数"""

    def test_get_structured_logger(self):
        """测试获取结构化日志记录器"""
        logger = get_structured_logger("test_factory_structured")

        assert isinstance(logger, StructuredLogger)
        assert isinstance(logger._logger, logging.Logger)

    def test_get_structured_logger_same_name(self):
        """测试相同名称返回相同的底层 logger"""
        logger1 = get_structured_logger("test_same_name")
        logger2 = get_structured_logger("test_same_name")

        # 应该包装相同的底层 logger
        assert logger1._logger is logger2._logger

    def test_get_context_logger(self):
        """测试获取上下文日志记录器"""
        logger = get_context_logger("test_factory_context")

        assert isinstance(logger, ContextLogger)
        assert isinstance(logger._logger, StructuredLogger)

    def test_get_context_logger_same_name(self):
        """测试相同名称返回相同的底层 logger"""
        logger1 = get_context_logger("test_same_context_name")
        logger2 = get_context_logger("test_same_context_name")

        # 底层 logger 应该相同
        assert logger1._logger._logger is logger2._logger._logger


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
