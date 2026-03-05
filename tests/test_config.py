"""
配置管理模块测试

测试 ConfigLoader 和 HotReloadConfig 类的所有功能。
"""

import logging
import os
from unittest.mock import Mock, patch

import pytest

from fish_async_task.config import (
    ConfigLoader,
    HotReloadConfig,
    validate_config,
)


class TestConfigLoader:
    """测试 ConfigLoader 类"""

    def test_init(self):
        """测试初始化"""
        logger = logging.getLogger(__name__)
        loader = ConfigLoader(logger)
        assert loader.logger == logger
        assert loader.MAX_TTL == 86400
        assert loader.MAX_TASK_STATUS_COUNT == 1000000

    def test_load_int_config_default(self):
        """测试加载默认整数配置"""
        loader = ConfigLoader(logging.getLogger(__name__))
        value = loader.load_int_config(
            "NON_EXISTENT_VAR", default_value=100, config_name="test_config"
        )
        assert value == 100

    def test_load_int_config_valid(self):
        """测试加载有效整数配置"""
        loader = ConfigLoader(logging.getLogger(__name__))
        os.environ["TEST_INT_VAR"] = "42"
        try:
            value = loader.load_int_config(
                "TEST_INT_VAR", default_value=100, config_name="test_config"
            )
            assert value == 42
        finally:
            os.environ.pop("TEST_INT_VAR", None)

    def test_load_int_config_min_value(self):
        """测试整数配置最小值验证"""
        loader = ConfigLoader(logging.getLogger(__name__))
        os.environ["TEST_INT_VAR"] = "-1"
        try:
            value = loader.load_int_config(
                "TEST_INT_VAR", default_value=100, config_name="test_config", min_value=1
            )
            assert value == 100  # 返回默认值
        finally:
            os.environ.pop("TEST_INT_VAR", None)

    def test_load_int_config_max_value(self):
        """测试整数配置最大值验证"""
        loader = ConfigLoader(logging.getLogger(__name__))
        os.environ["TEST_INT_VAR"] = "10000"
        try:
            value = loader.load_int_config(
                "TEST_INT_VAR", default_value=100, config_name="test_config", max_value=1000
            )
            assert value == 1000  # 返回最大值
        finally:
            os.environ.pop("TEST_INT_VAR", None)

    def test_load_int_config_invalid_format(self):
        """测试无效整数格式"""
        loader = ConfigLoader(logging.getLogger(__name__))
        os.environ["TEST_INT_VAR"] = "not_a_number"
        try:
            value = loader.load_int_config(
                "TEST_INT_VAR", default_value=100, config_name="test_config"
            )
            assert value == 100  # 返回默认值
        finally:
            os.environ.pop("TEST_INT_VAR", None)

    def test_load_timeout_config_none(self):
        """测试加载超时配置 - 未设置"""
        loader = ConfigLoader(logging.getLogger(__name__))
        with patch.dict(os.environ, {}, clear=True):
            value = loader.load_timeout_config(default_value=30.0)
            assert value == 30.0

    def test_load_timeout_config_valid(self):
        """测试加载有效超时配置"""
        loader = ConfigLoader(logging.getLogger(__name__))
        os.environ["TASK_TIMEOUT"] = "60.5"
        try:
            value = loader.load_timeout_config(default_value=30.0)
            assert value == 60.5
        finally:
            os.environ.pop("TASK_TIMEOUT", None)

    def test_load_timeout_config_negative(self):
        """测试负数超时配置"""
        loader = ConfigLoader(logging.getLogger(__name__))
        os.environ["TASK_TIMEOUT"] = "-10"
        try:
            value = loader.load_timeout_config(default_value=30.0)
            assert value is None  # 负数会禁用超时
        finally:
            os.environ.pop("TASK_TIMEOUT", None)

    def test_load_timeout_config_exceeds_max(self):
        """测试超时配置超过最大值"""
        loader = ConfigLoader(logging.getLogger(__name__))
        os.environ["TASK_TIMEOUT"] = "100000"
        try:
            value = loader.load_timeout_config(default_value=30.0)
            assert value == loader.MAX_TASK_TIMEOUT
        finally:
            os.environ.pop("TASK_TIMEOUT", None)

    def test_load_timeout_config_invalid_format(self):
        """测试无效超时格式"""
        loader = ConfigLoader(logging.getLogger(__name__))
        os.environ["TASK_TIMEOUT"] = "invalid"
        try:
            value = loader.load_timeout_config(default_value=30.0)
            assert value is None  # 无效格式禁用超时
        finally:
            os.environ.pop("TASK_TIMEOUT", None)

    def test_load_adaptive_worker_config(self):
        """测试加载自适应工作线程配置"""
        loader = ConfigLoader(logging.getLogger(__name__))
        config = loader.load_adaptive_worker_config()

        assert "adaptive_worker_enabled" in config
        assert "cpu_threshold" in config
        assert "queue_threshold_high" in config
        assert "queue_threshold_low" in config
        assert "scale_up_cooldown" in config
        assert "scale_down_cooldown" in config

    def test_load_adaptive_worker_config_custom(self):
        """测试加载自定义自适应工作线程配置"""
        loader = ConfigLoader(logging.getLogger(__name__))
        os.environ["ADAPTIVE_WORKER_ENABLED"] = "false"
        os.environ["WORKER_CPU_THRESHOLD"] = "0.7"
        os.environ["WORKER_QUEUE_THRESHOLD_HIGH"] = "200"
        os.environ["WORKER_QUEUE_THRESHOLD_LOW"] = "5"
        os.environ["WORKER_SCALE_UP_COOLDOWN"] = "10.0"
        os.environ["WORKER_SCALE_DOWN_COOLDOWN"] = "20.0"

        try:
            config = loader.load_adaptive_worker_config()
            assert config["adaptive_worker_enabled"] is False
            assert config["cpu_threshold"] == 0.7
            assert config["queue_threshold_high"] == 200
            assert config["queue_threshold_low"] == 5
            assert config["scale_up_cooldown"] == 10.0
            assert config["scale_down_cooldown"] == 20.0
        finally:
            os.environ.pop("ADAPTIVE_WORKER_ENABLED", None)
            os.environ.pop("WORKER_CPU_THRESHOLD", None)
            os.environ.pop("WORKER_QUEUE_THRESHOLD_HIGH", None)
            os.environ.pop("WORKER_QUEUE_THRESHOLD_LOW", None)
            os.environ.pop("WORKER_SCALE_UP_COOLDOWN", None)
            os.environ.pop("WORKER_SCALE_DOWN_COOLDOWN", None)

    def test_load_float_config(self):
        """测试加载浮点配置"""
        loader = ConfigLoader(logging.getLogger(__name__))
        os.environ["TEST_FLOAT_VAR"] = "3.14"
        try:
            value = loader._load_float_config(
                "TEST_FLOAT_VAR", default_value=2.0, config_name="test_float"
            )
            assert value == 3.14
        finally:
            os.environ.pop("TEST_FLOAT_VAR", None)

    def test_load_float_config_min_value(self):
        """测试浮点配置最小值验证"""
        loader = ConfigLoader(logging.getLogger(__name__))
        os.environ["TEST_FLOAT_VAR"] = "-0.5"
        try:
            value = loader._load_float_config(
                "TEST_FLOAT_VAR", default_value=1.0, config_name="test_float", min_value=0.0
            )
            assert value == 1.0  # 返回默认值
        finally:
            os.environ.pop("TEST_FLOAT_VAR", None)

    def test_load_float_config_max_value(self):
        """测试浮点配置最大值验证"""
        loader = ConfigLoader(logging.getLogger(__name__))
        os.environ["TEST_FLOAT_VAR"] = "2.0"
        try:
            value = loader._load_float_config(
                "TEST_FLOAT_VAR", default_value=1.0, config_name="test_float", max_value=1.5
            )
            assert value == 1.5  # 返回最大值
        finally:
            os.environ.pop("TEST_FLOAT_VAR", None)

    def test_load_bool_config_true(self):
        """测试加载布尔配置 - True"""
        loader = ConfigLoader(logging.getLogger(__name__))
        for true_value in [
            "true",
            "TRUE",
            "True",
            "1",
            "yes",
            "YES",
            "on",
            "ON",
            "enabled",
            "ENABLED",
        ]:
            os.environ["TEST_BOOL_VAR"] = true_value
            try:
                value = loader._load_bool_config("TEST_BOOL_VAR", default=False)
                assert value is True
            finally:
                os.environ.pop("TEST_BOOL_VAR", None)

    def test_load_bool_config_false(self):
        """测试加载布尔配置 - False"""
        loader = ConfigLoader(logging.getLogger(__name__))
        for false_value in [
            "false",
            "FALSE",
            "False",
            "0",
            "no",
            "NO",
            "off",
            "OFF",
            "disabled",
            "DISABLED",
        ]:
            os.environ["TEST_BOOL_VAR"] = false_value
            try:
                value = loader._load_bool_config("TEST_BOOL_VAR", default=True)
                assert value is False
            finally:
                os.environ.pop("TEST_BOOL_VAR", None)

    def test_load_bool_config_invalid(self):
        """测试无效布尔配置"""
        loader = ConfigLoader(logging.getLogger(__name__))
        os.environ["TEST_BOOL_VAR"] = "invalid"
        try:
            value = loader._load_bool_config("TEST_BOOL_VAR", default=True)
            assert value is True  # 返回默认值
        finally:
            os.environ.pop("TEST_BOOL_VAR", None)

    def test_load_bool_config_not_set(self):
        """测试未设置布尔配置"""
        loader = ConfigLoader(logging.getLogger(__name__))
        value = loader._load_bool_config("NON_EXISTENT_BOOL_VAR", default=True)
        assert value is True

    def test_load_performance_config(self):
        """测试加载性能优化配置"""
        loader = ConfigLoader(logging.getLogger(__name__))
        config = loader.load_performance_config()

        assert "shard_count" in config
        assert "batch_update_buffer_size" in config
        assert "batch_update_interval" in config
        assert "enable_auto_cleanup" in config
        assert "enable_batch_updates" in config
        assert "enable_adaptive_scaling" in config

    def test_load_performance_config_custom(self):
        """测试加载自定义性能优化配置"""
        loader = ConfigLoader(logging.getLogger(__name__))
        os.environ["SHARD_COUNT"] = "32"
        os.environ["BATCH_UPDATE_BUFFER_SIZE"] = "200"
        os.environ["BATCH_UPDATE_INTERVAL"] = "0.5"
        os.environ["ENABLE_AUTO_CLEANUP"] = "false"
        os.environ["ENABLE_BATCH_UPDATES"] = "true"
        os.environ["ENABLE_ADAPTIVE_SCALING"] = "true"

        try:
            config = loader.load_performance_config()
            assert config["shard_count"] == 32
            assert config["batch_update_buffer_size"] == 200
            assert config["batch_update_interval"] == 0.5
            assert config["enable_auto_cleanup"] is False
            assert config["enable_batch_updates"] is True
            assert config["enable_adaptive_scaling"] is True
        finally:
            os.environ.pop("SHARD_COUNT", None)
            os.environ.pop("BATCH_UPDATE_BUFFER_SIZE", None)
            os.environ.pop("BATCH_UPDATE_INTERVAL", None)
            os.environ.pop("ENABLE_AUTO_CLEANUP", None)
            os.environ.pop("ENABLE_BATCH_UPDATES", None)
            os.environ.pop("ENABLE_ADAPTIVE_SCALING", None)


class TestHotReloadConfig:
    """测试 HotReloadConfig 类"""

    def test_init_default(self):
        """测试默认初始化"""
        config = HotReloadConfig()
        assert config._reload_interval == 60
        assert config._last_reload == 0.0
        assert config._config_cache == {}
        assert config._config_parsers == {}

    def test_init_custom(self):
        """测试自定义初始化"""
        logger = logging.getLogger(__name__)
        config = HotReloadConfig(logger=logger, reload_interval=30)
        assert config.logger == logger
        assert config._reload_interval == 30

    def test_register_config(self):
        """测试注册配置项"""
        config = HotReloadConfig()

        def parser():
            return "value"

        config.register_config("test_key", parser, default="default")
        assert "test_key" in config._config_parsers
        assert config._config_parsers["test_key"]["parser"] == parser
        assert config._config_parsers["test_key"]["default"] == "default"

    def test_get_cached(self):
        """测试获取缓存的配置"""
        config = HotReloadConfig()

        def parser():
            return "parsed_value"

        config.register_config("test_key", parser, default="default")
        # 先触发一次解析来填充缓存
        config.get("test_key", use_cache=False)

        # 现在缓存应该有值
        cached_value = config._config_cache.get("test_key")
        assert cached_value == "parsed_value"

        # 使用缓存获取应该返回相同的值
        value = config.get("test_key", use_cache=True)
        assert value == "parsed_value"

    def test_get_not_cached(self):
        """测试获取未缓存的配置"""
        config = HotReloadConfig()

        def parser():
            return "parsed_value"

        config.register_config("test_key", parser, default="default")

        value = config.get("test_key", use_cache=False)
        assert value == "parsed_value"
        assert config._config_cache["test_key"] == "parsed_value"

    def test_get_nonexistent(self):
        """测试获取不存在的配置"""
        config = HotReloadConfig()
        value = config.get("nonexistent_key")
        assert value is None

    def test_get_parser_returns_none(self):
        """测试解析器返回 None 时使用默认值"""
        config = HotReloadConfig()

        def parser():
            return None

        config.register_config("test_key", parser, default="default")
        value = config.get("test_key", use_cache=False)
        assert value == "default"

    def test_get_parser_raises_exception(self):
        """测试解析器抛出异常时使用默认值"""
        config = HotReloadConfig()

        def parser():
            raise ValueError("Parse error")

        config.register_config("test_key", parser, default="default")
        value = config.get("test_key", use_cache=False)
        assert value == "default"

    def test_reload(self):
        """测试重载配置"""
        config = HotReloadConfig()

        call_count = {"count": 0}

        def parser():
            call_count["count"] += 1
            return f"value_{call_count['count']}"

        config.register_config("test_key", parser, default="default")

        # 第一次重载
        reloaded = config.reload()
        assert reloaded == 1
        assert config._config_cache["test_key"] == "value_1"

        # 第二次重载
        reloaded = config.reload()
        assert reloaded == 1
        assert config._config_cache["test_key"] == "value_2"

    def test_reload_multiple_configs(self):
        """测试重载多个配置"""
        config = HotReloadConfig()

        config.register_config("key1", lambda: "value1", "default1")
        config.register_config("key2", lambda: "value2", "default2")
        config.register_config("key3", lambda: "value3", "default3")

        reloaded = config.reload()
        assert reloaded == 3

    def test_reload_with_exception(self):
        """测试重载时部分解析器失败"""
        config = HotReloadConfig()

        def failing_parser():
            raise ValueError("Parse error")

        config.register_config("key1", lambda: "value1", "default1")
        config.register_config("key2", failing_parser, "default2")
        config.register_config("key3", lambda: "value3", "default3")

        reloaded = config.reload()
        # 应该继续重载其他配置（key1 和 key3）
        assert reloaded >= 2
        assert config._config_cache.get("key1") == "value1"
        # 失败的解析器不会将默认值放入缓存
        assert config._config_cache.get("key2") is None
        assert config._config_cache.get("key3") == "value3"

    def test_get_all(self):
        """测试获取所有配置"""
        config = HotReloadConfig()

        config.register_config("key1", lambda: "value1", "default1")
        config.register_config("key2", lambda: "value2", "default2")

        # 首先重载以填充缓存
        config.reload()

        all_configs = config.get_all()
        assert all_configs["key1"] == "value1"
        assert all_configs["key2"] == "value2"

    def test_clear_cache(self):
        """测试清除缓存"""
        config = HotReloadConfig()

        config.register_config("test_key", lambda: "value", "default")
        config._config_cache["test_key"] = "cached_value"
        config._last_reload = 123.456

        config.clear_cache()

        assert config._config_cache == {}
        assert config._last_reload == 0.0


class TestValidateConfig:
    """测试配置验证装饰器"""

    def test_validate_with_min_value(self):
        """测试最小值验证"""

        @validate_config(min_value=10, default=5)
        def get_value():
            return 15

        assert get_value() == 15

    def test_validate_with_min_value_violated(self):
        """测试最小值违规"""

        @validate_config(min_value=10, default=5)
        def get_value():
            return 5

        assert get_value() == 5  # 返回默认值

    def test_validate_with_max_value(self):
        """测试最大值验证"""

        @validate_config(max_value=100, default=50)
        def get_value():
            return 75

        assert get_value() == 75

    def test_validate_with_max_value_violated(self):
        """测试最大值违规"""

        @validate_config(max_value=100, default=50)
        def get_value():
            return 150

        assert get_value() == 50  # 返回默认值

    def test_validate_with_allowed_values(self):
        """测试允许值列表"""

        @validate_config(allowed_values=["a", "b", "c"], default="a")
        def get_value():
            return "b"

        assert get_value() == "b"

    def test_validate_with_allowed_values_violated(self):
        """测试允许值违规"""

        @validate_config(allowed_values=["a", "b", "c"], default="a")
        def get_value():
            return "d"

        assert get_value() == "a"  # 返回默认值

    def test_validate_returns_none(self):
        """测试返回 None 时使用默认值"""

        @validate_config(min_value=10, default=5)
        def get_value():
            return None

        assert get_value() == 5

    def test_validate_no_constraints(self):
        """测试无约束"""

        @validate_config(default=0)
        def get_value():
            return 42

        assert get_value() == 42

    def test_validate_combined_constraints(self):
        """测试组合约束"""

        @validate_config(
            min_value=0, max_value=100, allowed_values=[10, 20, 30, 40, 50], default=10
        )
        def get_value():
            return 25

        # 不在允许列表中，返回默认值
        assert get_value() == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
