"""
性能模块日志配置测试

测试 _logging.py 中的日志配置功能。
"""

import logging
import re
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from fish_async_task.performance import _logging
from fish_async_task.performance._logging import (
    configure_logging,
    get_logger,
)
from fish_async_task.performance._logging import logger as module_logger


class TestConfigureLogging:
    """测试 configure_logging 函数"""

    def test_configure_logging_sets_level(self):
        """测试配置设置日志级别"""
        # 保存原始级别
        original_level = module_logger.level

        configure_logging(logging.WARNING)
        assert module_logger.level == logging.WARNING

        # 恢复原始级别
        configure_logging(original_level)

    def test_configure_logging_adds_handler(self):
        """测试配置添加处理器"""
        # 清除现有处理器
        original_handlers = module_logger.handlers.copy()
        module_logger.handlers.clear()

        configure_logging(logging.INFO)

        # 应该添加了一个处理器
        assert len(module_logger.handlers) >= 1

        # 验证处理器类型
        assert any(isinstance(h, logging.StreamHandler) for h in module_logger.handlers)

        # 恢复原始处理器
        module_logger.handlers.clear()
        module_logger.handlers.extend(original_handlers)

    def test_configure_logging_adds_handler_once(self):
        """测试不会重复添加处理器"""
        # 保存原始状态
        original_handlers_count = len(module_logger.handlers)

        configure_logging(logging.INFO)
        after_first = len(module_logger.handlers)

        configure_logging(logging.WARNING)
        after_second = len(module_logger.handlers)

        # 处理器数量应该相同或减少（因为去重检查）
        assert after_second <= after_first

    def test_configure_logging_formatter(self):
        """测试日志格式设置"""
        # 获取第一个 StreamHandler
        handler = None
        for h in module_logger.handlers:
            if isinstance(h, logging.StreamHandler):
                handler = h
                break

        if handler:
            formatter = handler.formatter
            assert isinstance(formatter, logging.Formatter)

            # 测试格式
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test message",
                args=(),
                exc_info=None,
            )
            formatted = formatter.format(record)

            assert "test" in formatted
            assert "INFO" in formatted
            assert "Test message" in formatted

    def test_configure_logging_levels(self):
        """测试各种日志级别"""
        original_level = module_logger.level

        for level in [
            logging.DEBUG,
            logging.INFO,
            logging.WARNING,
            logging.ERROR,
            logging.CRITICAL,
        ]:
            configure_logging(level)
            assert module_logger.level == level

        # 恢复
        configure_logging(original_level)


class TestGetLogger:
    """测试 get_logger 函数"""

    def test_get_logger_returns_logger(self):
        """测试返回正确的 logger 类型"""
        returned_logger = get_logger()
        assert isinstance(returned_logger, logging.Logger)

    def test_get_logger_same_instance(self):
        """测试多次调用返回相同实例"""
        logger1 = get_logger()
        logger2 = get_logger()

        assert logger1 is logger2

    def test_get_logger_name(self):
        """测试 logger 名称"""
        returned_logger = get_logger()
        assert returned_logger.name == "fish_async_task.performance._logging"


class TestDefaultConfiguration:
    """测试默认配置行为"""

    def test_module_logger_exists(self):
        """测试模块级 logger 存在"""
        assert module_logger is not None
        assert isinstance(module_logger, logging.Logger)

    def test_module_logger_name(self):
        """测试模块 logger 名称"""
        assert module_logger.name == "fish_async_task.performance._logging"

    def test_module_logger_has_handlers(self):
        """测试模块 logger 有处理器（默认配置）"""
        # 由于模块导入时会自动配置，应该有处理器
        assert len(module_logger.handlers) > 0

    def test_module_logger_can_log(self):
        """测试模块 logger 可以记录日志"""
        # 添加 StringIO handler 来捕获输出
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.INFO)
        module_logger.addHandler(handler)
        original_level = module_logger.level
        module_logger.setLevel(logging.INFO)

        module_logger.info("Test message from module logger")

        output = stream.getvalue()
        assert "Test message from module logger" in output

        # 清理
        module_logger.removeHandler(handler)
        module_logger.setLevel(original_level)


class TestLoggerLevels:
    """测试日志级别相关功能"""

    def test_logger_level_debug(self):
        """测试 DEBUG 级别"""
        original_level = module_logger.level
        configure_logging(logging.DEBUG)

        assert module_logger.level == logging.DEBUG

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.DEBUG)
        module_logger.addHandler(handler)

        module_logger.debug("Debug message")
        assert "Debug message" in stream.getvalue()

        module_logger.removeHandler(handler)
        configure_logging(original_level)

    def test_logger_level_info(self):
        """测试 INFO 级别"""
        original_level = module_logger.level
        configure_logging(logging.INFO)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.INFO)
        module_logger.addHandler(handler)

        module_logger.debug("Debug message")
        # DEBUG 级别低于 INFO，可能不会显示
        debug_output = stream.getvalue()

        stream.truncate(0)
        stream.seek(0)

        module_logger.info("Info message")
        assert "Info message" in stream.getvalue()

        module_logger.removeHandler(handler)
        configure_logging(original_level)

    def test_logger_level_warning(self):
        """测试 WARNING 级别"""
        original_level = module_logger.level
        configure_logging(logging.WARNING)

        assert module_logger.level == logging.WARNING

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.WARNING)
        module_logger.addHandler(handler)

        module_logger.warning("Warning message")
        assert "Warning message" in stream.getvalue()

        module_logger.removeHandler(handler)
        configure_logging(original_level)

    def test_logger_level_error(self):
        """测试 ERROR 级别"""
        original_level = module_logger.level
        configure_logging(logging.ERROR)

        assert module_logger.level == logging.ERROR

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.ERROR)
        module_logger.addHandler(handler)

        module_logger.error("Error message")
        assert "Error message" in stream.getvalue()

        module_logger.removeHandler(handler)
        configure_logging(original_level)

    def test_logger_level_critical(self):
        """测试 CRITICAL 级别"""
        original_level = module_logger.level
        configure_logging(logging.CRITICAL)

        assert module_logger.level == logging.CRITICAL

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.CRITICAL)
        module_logger.addHandler(handler)

        module_logger.critical("Critical message")
        assert "Critical message" in stream.getvalue()

        module_logger.removeHandler(handler)
        configure_logging(original_level)


class TestLoggerPropagation:
    """测试日志传播行为"""

    def test_logger_propagation_default(self):
        """测试默认的传播行为"""
        # 创建一个新的测试 logger
        test_logger = logging.getLogger("test_perf_propagation")

        # 默认情况下，传播应该启用
        assert test_logger.propagate is True

    def test_logger_level_propagation(self):
        """测试级别传播"""
        # 获取根 logger
        root_logger = logging.getLogger()

        # 设置根 logger 级别
        original_level = root_logger.level
        root_logger.setLevel(logging.WARNING)

        # 创建子 logger
        child_logger = logging.getLogger("test_perf_child.test_child")
        child_logger.setLevel(logging.DEBUG)

        # 添加 handler 到根 logger
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.WARNING)
        root_logger.addHandler(handler)

        # 子 logger 的 INFO 消息不应该出现在根 logger
        child_logger.info("Child info message")
        assert "Child info message" not in stream.getvalue()

        # 子 logger 的 WARNING 消息应该传播到根 logger
        child_logger.warning("Child warning message")
        assert "Child warning message" in stream.getvalue()

        # 清理
        root_logger.removeHandler(handler)
        root_logger.setLevel(original_level)


class TestFormatterOutput:
    """测试格式化输出"""

    def test_default_format_includes_timestamp(self):
        """测试默认格式包含时间戳"""
        # 获取第一个 StreamHandler
        handler = None
        for h in module_logger.handlers:
            if isinstance(h, logging.StreamHandler):
                handler = h
                break

        if handler and handler.formatter:
            formatter = handler.formatter

            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test message",
                args=(),
                exc_info=None,
            )
            formatted = formatter.format(record)

            # 默认格式应该包含时间戳模式
            assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", formatted)

    def test_default_format_includes_level(self):
        """测试默认格式包含日志级别"""
        handler = None
        for h in module_logger.handlers:
            if isinstance(h, logging.StreamHandler):
                handler = h
                break

        if handler and handler.formatter:
            formatter = handler.formatter

            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Test message",
                args=(),
                exc_info=None,
            )
            formatted = formatter.format(record)

            assert "ERROR" in formatted

    def test_default_format_includes_name(self):
        """测试默认格式包含 logger 名称"""
        handler = None
        for h in module_logger.handlers:
            if isinstance(h, logging.StreamHandler):
                handler = h
                break

        if handler and handler.formatter:
            formatter = handler.formatter

            record = logging.LogRecord(
                name="my_test_logger",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test message",
                args=(),
                exc_info=None,
            )
            formatted = formatter.format(record)

            assert "my_test_logger" in formatted


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
